# Spike — WinRT `Windows.ApplicationModel.StartupTask` for packaged-aware autostart

**Status:** PoC complete for the unpackaged/from-source path. Packaged-MSIX path
**explicitly deferred** — user will verify against a real Store app build
(RULE-SPIKE1 point 4/5/6 for the packaged branch: not suite-verified, not
spike-verified, pending a live check outside this session).
**Related:** RULE-SPIKE1, RULE-WIN9, RULE-WIN10, RULE-WIN11, `docs/spikes/startup-com-reentrancy.md`.

## RULE-REQ2 failure paragraph — why the current autostart checkbox is being replaced, not iterated on

The Settings page checkbox ("Start NetSentinel automatically when Windows
starts") calls `set_run_on_startup()` ([system_tray.py:54-73](../../ui/system_tray.py#L54-L73))
unconditionally, on every platform, which writes a plain
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value. That mechanism has
no concept of package identity or user/policy consent state — it is a bare
registry write with no feedback channel. On a Store/MSIX-packaged install this
is the wrong primitive: Windows' supported autostart surface for packaged apps
is the `uap5:StartupTask` manifest extension + `Windows.ApplicationModel.
StartupTask` runtime API, not the classic Run key. A packaged app's Run-key
entry is not what Task Manager's "Startup apps" tab or Settings > Apps >
Startup manage, so the checkbox can read back "checked" from its own registry
write (`get_run_on_startup()`) while Windows silently never honors it as
autostart for that packaging context — the "lying checkbox" the plan names.
Nothing has been tried yet to fix this (no prior attempt exists); this spike
is the first step of the correct fix — a package-identity-aware backend
selector (`modules/autostart.py`, section 5.3 of the plan) — rather than a
patch to the Run-key path, because the Run key structurally cannot express
`DisabledByUser`/`DisabledByPolicy`/`EnabledByPolicy`, states only
`Windows.ApplicationModel.StartupTask` exposes.

## Method

`scratchpad/spike_startup_task.py` (not in-tree — throwaway PoC run via a
subprocess so a wrong vtable index, an access violation rather than a Python
exception, cannot take down anything but that child process). Guarded with
`SetErrorMode(SEM_NOGPFAULTERRORBOX | SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)`
so a fault terminates cleanly instead of blocking on an unattended WER dialog.

All IIDs and vtable slot indices below are **transcribed, not guessed**, from
the installed Windows SDK:

```
C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\winrt\windows.applicationmodel.h
C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\winrt\asyncinfo.h
```

(SDK 10.0.26100.0 confirmed installed alongside 10.0.18362.0 on this machine;
the StartupTask interfaces are identical in shape across both.)

## 1. `RoInitialize(RO_INIT_MULTITHREADED)` — Qt GUI thread vs. a fresh thread

| Thread | Raw HRESULT | Meaning |
|---|---|---|
| Bare process main thread, no Qt anywhere in the process | `S_OK` (0) | Clean MTA init — expected, nothing claimed this apartment yet |
| Fresh `threading.Thread` spawned from that bare process | `S_OK` (0) | Clean MTA init — a genuinely new thread has no apartment state |
| **Qt GUI thread, `QApplication` already constructed** | **`RPC_E_CHANGED_MODE`** (`0x80010106`) | **Confirmed** — Qt's `QApplication` implicitly calls `CoInitializeEx(COINIT_APARTMENTTHREADED)` for OLE drag/drop support; COM refuses to switch that thread's apartment to MTA |
| `threading.Thread` spawned **while the Qt `QApplication` is alive in the same process** | `S_OK` (0) | **Confirmed** — a plain background thread's apartment is independent of the GUI thread's STA; `RoInitialize(MULTITHREADED)` there is unaffected by Qt |

This directly validates the plan's 5.2/5.3 design: `workers/autostart_worker.py`
must be a `QThread` calling `RoInitialize`/`RoUninitialize` in its own
`run()`/`finally` — never on the GUI thread, and it will get a clean MTA
regardless of Qt's STA on the main thread. Point 1 of the spike's task list is
answered with a live measurement, not an assumption.

## 2. HSTRING round-trip integrity

```json
{
  "create_hr": "S_OK",
  "roundtrip_ok": true,
  "pointer_is_64bit_significant": true,
  "delete_hr": "S_OK"
}
```

`WindowsCreateString("Windows.ApplicationModel.StartupTask", ...)` →
`WindowsGetStringRawBuffer` → exact string readback, and the HSTRING handle's
pointer value exceeds `0xFFFFFFFF` (a genuine 64-bit-significant value) —
confirming a **local** `ctypes.WinDLL("combase.dll")` handle with explicit
`restype`/`argtypes` on every call (RULE-WIN11) does not truncate the handle.
No use of `ctypes.windll.combase.X` anywhere (that form mutates process-global
cached function objects — RULE-WIN11's other corollary).

## 3. Raw `RoGetActivationFactory` HRESULT — unpackaged, from source

```json
{"hresult": "S_OK", "raw_hresult_int": 0}
```

**Result diverges from the pre-spike assumption.** Factory activation for
`Windows.ApplicationModel.StartupTask` via `IID_IStartupTaskStatics`
(`ee5b60bd-a148-41a7-b26e-e8b88a1e62f8`) **succeeds even unpackaged, running
from source** (`python app.py`, no package identity, no manifest). This makes
sense on reflection: the *factory class* is a system-provided WinRT type
available process-wide; it is the *operation*, not the *activation*, that
needs package identity.

## 4. Vtable slot indices + IIDs — cited, not transcribed from memory

**`IStartupTaskStatics`** — IID `ee5b60bd-a148-41a7-b26e-e8b88a1e62f8`
(`windows.applicationmodel.h:5634`, SDK path cited above):

| Slot | Method |
|---|---|
| 0-2 | `IUnknown`: QueryInterface, AddRef, Release |
| 3-5 | `IInspectable`: GetIids, GetRuntimeClassName, GetTrustLevel |
| 6 | `GetForCurrentPackageAsync(IAsyncOperation<IVectorView<StartupTask>>**)` |
| 7 | `GetAsync(HSTRING taskId, IAsyncOperation<StartupTask>**)` |

**`IStartupTask`** — IID `f75c23c8-b5f2-4f6c-88dd-36cb1d599d17`:

| Slot | Method |
|---|---|
| 6 | `RequestEnableAsync(IAsyncOperation<StartupTaskState>**)` |
| 7 | `Disable()` |
| 8 | `get_State(StartupTaskState*)` |
| 9 | `get_TaskId(HSTRING*)` |

**`IAsyncOperation<StartupTask>`** (the type `GetAsync` returns — a
*parameterized* interface, but its IID is **never needed**: `GetAsync` hands
it back directly as a typed out-param, no `QueryInterface` required):

| Slot | Method |
|---|---|
| 6 | `put_Completed(handler)` — **not used**, see "Await strategy" below |
| 7 | `get_Completed(handler**)` — not used |
| 8 | `GetResults(IStartupTask**)` |

**`IAsyncInfo`** — IID `00000036-0000-0000-C000-000000000046`
(`asyncinfo.h:114`, SDK path cited above) —
**well-known, not parameterized**, obtained via `QueryInterface` on the
`IAsyncOperation<StartupTask>` pointer:

| Slot | Method |
|---|---|
| 6 | `get_Id(uint32*)` |
| 7 | `get_Status(AsyncStatus*)` |
| 8 | `get_ErrorCode(HRESULT*)` |
| 9 | `Cancel()` |
| 10 | `Close()` |

`StartupTaskState`: `Disabled=0, DisabledByUser=1, Enabled=2,
DisabledByPolicy=3 (contract v2), EnabledByPolicy=4 (contract v3)`.
`AsyncStatus`: `Started=0, Completed=1, Canceled=2, Error=3`.

The full call chain (`QueryInterface`, `GetAsync`, `get_Status` polling,
`GetResults`) was exercised live via raw ctypes vtable dispatch (read the
vtable pointer from the object's first 8 bytes, index into it, call) — **zero
crashes across the run**, which is itself evidence the indices above are
correct: a wrong slot on a 10-13-method interface is far more likely to
produce an access violation or garbage return than a clean, semantically
correct Win32-mapped HRESULT (see §5).

## 5. `GetAsync` completion — unpackaged result

```json
{
  "get_async_hr": "0x80070490",
  "async_op_ptr": null
}
```

`0x80070490` = `HRESULT_FROM_WIN32(ERROR_NOT_FOUND)`. `GetAsync` fails
**synchronously** (the call itself returns the error — no async operation
object is even produced, `async_op_ptr` is null) because there is no
`<uap5:StartupTask Id="NetSentinelStartupTask">` entry in any package manifest
to resolve unpackaged — there is no package manifest at all. This is the
clean, expected boundary: **factory activation succeeds without package
identity; the actual task lookup does not.** Confirms the plan's framing that
`GetAsync` is a manifest lookup, and shows exactly what "manifest lookup with
nothing to find" looks like.

Poll count / completion time and `RequestEnableAsync` consent-dialog behaviour
(spike items 5 and 6) were **not reached** — both require a resolved
`IStartupTask` instance, which needs a real `uap5:StartupTask` manifest entry,
i.e. a packaged build.

## 6. Packaged-MSIX path — deferred by user decision

No signed test MSIX was built or sideloaded this session (`Get-AppxPackage`
confirms nothing named NetSentinel is currently installed). **Per explicit
user instruction, this spike does not attempt that now** — the user will
verify the packaged path directly against a real Store app build instead of a
local sideload test. Recorded honestly, per the plan's own verification
section: **the packaged branch is neither suite-verified nor spike-verified
by this document** — items 3 (packaged `RoGetActivationFactory`), 5 (`GetAsync`
completion against a real manifest entry), and 6 (`RequestEnableAsync` consent
dialog vs. `Disabled`/`DisabledByUser`) remain open until that check happens.
`modules/startup_task.py`'s raw-accessor design (returning `(hresult, state)`
rather than a boolean, RULE-WIN11) means that check will be a matter of
running the real accessor and reading the HRESULT — no new instrumentation
needed at that point.

## 7. PyInstaller frozen-exe check

N/A in the sense that nothing needs bundling: `combase.dll` is a System32
component ctypes loads by name via the standard DLL search path regardless of
whether the process is a frozen PyInstaller exe or `python app.py` from
source — this is unrelated to Python's import machinery (`hiddenimports` in
`NetSentinel.spec`, RULE-B1) since no new Python package is added. This spike
adds zero new pip dependencies (session-workflow.md: no new deps without an
explicit ask) — `modules/startup_task.py` will be pure `ctypes` against
already-present system DLLs, same shape as the existing `fix_maximized_restore_rect()`
pattern in `ui/app_settings.py`.

The one PyInstaller-relevant unknown that *does* carry to the packaged branch:
whether `sys.frozen`/`sys.executable` resolution inside an MSIX container
(`AppData\Local\Programs\...` virtualized path, or the `WindowsApps` package
folder) affects anything `modules/startup_task.py` touches. It does not,
by design — `StartupTask` activation never passes an exe path; the package
manifest's `<Application Executable>` is what Windows launches, which is
exactly why this API exists instead of a Run-key string. Recorded here so a
future reader doesn't re-derive it.

## Decision to record (per plan, restated for traceability)

**Keep `Enabled="false"` in the manifest's `uap5:StartupTask` entry.**
`"true"` auto-starts for every user at install with no consent — contrary to
the app's "all off by default" posture (project-vision Non-Goals) and a
plausible Store-certification friction point. `RequestEnableAsync` exists
precisely so the app can ask, from an explicit user gesture (the settings
checkbox or the tray menu item — the only two call sites, per plan 5.4). It
also costs nothing on the failure path: a user or policy that set
`DisabledByUser`/`DisabledByPolicy` cannot be overridden by flipping the
manifest attribute — `RequestEnableAsync` would just surface that same denial
back through the API instead of a silent manifest override.

## Await strategy — confirmed: poll `IAsyncInfo::get_Status`, never `put_Completed`

Validated live, not just reasoned:

1. **No parameterized IID was ever computed or needed.** `GetAsync` returns
   the `IAsyncOperation<StartupTask>*` directly as a typed out-param; polling
   only requires `QueryInterface(IID_IAsyncInfo)` — a single well-known,
   non-parameterized GUID, confirmed working live (§4/§5). Using
   `put_Completed`/`AsyncOperationCompletedHandler<StartupTask>` instead would
   require synthesising a genuinely new interface — a vtable **Windows calls
   into** — whose IID is a SHA-1 hash of a type signature with no header
   literal to transcribe (unlike everything measured above). That is the
   exact reentrancy shape RULE-WIN9's postmortem describes as this codebase's
   recurring native-fault source; avoided entirely by polling instead.
2. `GetAsync` on an unpackaged caller returned synchronously in the same call
   (§5) — no polling loop even ran in this measurement. Once a real
   `uap5:StartupTask` entry exists (packaged path), expect a genuine async
   operation object; the poll loop in `spike_startup_task.py`
   (10 ms interval, 2 s deadline) is already written and exercised code,
   ready to reuse verbatim in `modules/startup_task.py`.
3. MTA requirement for polling (§1) is confirmed independent of whatever the
   Qt GUI thread's apartment state is — couples cleanly to the `QThread`
   design in 5.3 with no additional constraint discovered.

## Verdict

**Unpackaged/from-source path: fully measured, zero surprises requiring a
design change.** The factory-activates-but-task-lookup-fails split (§3 vs §5)
is new information beyond the plan's original framing but changes nothing
about the design — `modules/autostart.py`'s `autostart_backend()` already
routes non-Store installs to the Run-key path (`is_store_app()` is `False`
from source), so this codepath is exercised only when `autostart_backend()`
is deliberately forced to `"startup_task"` for testing, never in the shipped
non-Store branch.

**Packaged/MSIX path: deferred to the user's own Store-app verification**,
not attempted locally this session. `modules/startup_task.py`'s raw
`(hresult, state)` accessor contract (5.3) is designed exactly so that
verification is "run it and read the HRESULT" — no mock, no boolean hiding
"answered no" from "never ran" (RULE-WIN11's lesson, applied up front instead
of discovered after a v2.1.33-style regression).

**Proceed to implementation (5.2-5.5)** using the vtable/IID map in §4,
unchanged from the plan's design.
