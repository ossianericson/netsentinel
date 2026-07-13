# Spike — `0x8001010d` at startup: the UIA / COM one-time-init fault

**Status:** ROOT-CAUSED AND FIXED (2026-07-13). See RULE-WIN10.
**Fix:** `ui/uia_warmup.py` + two call sites in `app.py`. Guarded by `tests/test_uia_warmup.py`.

> **Note.** An earlier revision of this document blamed the splash screen's nested
> `processEvents()` pump and proposed three fix directions built on that theory. **All three
> were wrong**, and are preserved below under "The splash theory, and why it was wrong" so the
> next person does not rediscover them. The splash is not involved.

---

## One-line summary

The **first `WM_GETOBJECT` the process ever answers** makes Qt call
`UiaReturnRawElementProvider`, whose one-time UIAutomationCore init needs an outgoing
`CoCreateInstance`. `WM_GETOBJECT` is always delivered as an input-synchronous cross-process
`SendMessage`, and COM forbids outgoing calls from a thread in that state →
`RPC_E_CANTCALLOUT_ININPUTSYNCCALL` (`0x8001010d`), raised as SEH and logged by `faulthandler`.
**The process survives** — it is a first-chance, fully-handled COM exception.

The monkey harness *is* the UIA client, and it fails any run that appends a new crash-log entry
(RULE-CHAOS2 — correctly). Every launch appended one, so every phase aborted.

---

## Mechanism (native stack, `procdump -e 1 -f 8001010d` + `cdb -z … -c ".ecxr; kb"`)

Read bottom-up. The Python frames are only *where the main thread happened to be*; the culprit
is the top half.

```
python311!PyEval_EvalFrameDefault            <- main()
Qt6Widgets!QSplashScreen::setPixmap          <- pumps events internally (Qt does this itself)
Qt6Core!QEventDispatcherWin32::processEvents
user32!PeekMessageW
ntdll!KiUserCallbackDispatcherContinue       <- kernel calls back into our WndProc
user32!UserCallWinProcCheckWow               <- dispatching WM_GETOBJECT
qwindows!…                                   <- QWindowsUiaAccessibility::handleWmGetObject
UIAutomationCore!UiaReturnRawElementProvider
UIAutomationCore!CheckInit                   <- ONE-TIME lazy init. THIS is the bug.
UIAutomationCore!DoInit
UIAutomationCore!CUIAutomation7::FinalConstruct
UIAutomationCore!BlockingCoreDispatcher::CreateAndRegisterBlockingCore
combase!CoCreateInstance                     <- the illegal OUTGOING COM call
combase!CProcessActivator::CreateInstance    <- refuses: RPC_E_CANTCALLOUT_ININPUTSYNCCALL
```

`CheckInit` is the whole story: UIAutomationCore initialises itself lazily, on first use, and
that init calls out to COM. It happens **once per process** and never again.

`faulthandler.enable()` on Windows installs a **vectored** exception handler
(`AddVectoredExceptionHandler`), i.e. a *first-chance* handler. It logs any SEH exception with
the high bit set and then returns `EXCEPTION_CONTINUE_SEARCH`, so normal handling proceeds. That
is why the log grows but nothing dies.

---

## Evidence

| Experiment | Result |
|---|---|
| Real `app.py`, **no** UIA client, full startup | **clean** (+0 bytes) |
| Real `app.py`, UIA client attached during startup | fault (once) |
| Real `app.py`, UIA client attached **15 s after `app.exec()` is pumping** | **fault** (once) |
| `procdump` armed for 3 dumps, 12 further UIA tree walks | exactly **1** dump — once per process |
| Bare 40-line PyQt app (no splash, no threads, no NetSentinel code) | **fault reproduces** |
| Same bare app + warmup | **clean** |
| `a2eaa78` (before Phase 3 existed), flag off | fault — native chrome is not the cause |

The bare-PyQt-app reproduction is the decisive one: no splash, no `processEvents()` pump, no
tray icon, no native chrome, no worker threads. Just a `QMainWindow` and a UIA client.

---

## The splash theory, and why it was wrong

The Python traceback always pointed at `_splash_msg` / `processEvents`, and the crash log holds
128+ such entries across many `app.py` line numbers going back months. That made the nested
splash pump look like the defect. It is not.

The fault fires on the **first** `WM_GETOBJECT` the process answers. The harness connects as
early as it possibly can, so that first message almost always lands during startup — while
`main()` happens to be inside a splash pump. The splash is the *scenery*, not the cause. Attach
the client later and the fault simply lands somewhere else (measured above).

This also explains the "unresolved race" the previous revision recorded (five clean flag-off
runs, then one that faulted 45/45): it was never a race in the pump. It is simply *whether a UIA
client connects at all*.

**Consequence:** the three fix directions the previous revision proposed — restructure the
splash, hide the splash from the UIA tree, defer Qt accessibility — would all have failed. They
address condition (b) "the thread is in an input-sync call", which is true of *every*
`WM_GETOBJECT` dispatch, in `app.exec()` just as much as in a nested pump. None of them removes
condition (a), the one-time `CoCreateInstance`.

The same trap already burned three earlier attempts, recorded in
`docs/spikes/startup-com-reentrancy.md`: Fix 1 (`singleShot(0)` on the tray icon), Fix 2 (move
`.show()` to `showEvent`), Fix 3 (guard every native tray method). All three chased
`Shell_NotifyIcon`. All three were confirmed ineffective, because the tray icon was never
involved either.

---

## The fix

Do the one-time init ourselves, from a context where the COM call-out is legal. A **same-thread**
`SendMessage` is a direct WndProc call — the thread is *not* inside an input-synchronous call
(`InSendMessage()` is false) — so the `CoCreateInstance` succeeds.

```python
# app.py, immediately after _splash.show()
warm_up_uia_provider(int(_splash.winId()))     # ~3 ms, once
```

`ui/uia_warmup.py` sends `WM_GETOBJECT` / `UIA_ROOT_OBJECT_ID` to our own window and checks the
`LRESULT`: non-zero means Qt handed UIA a provider, so `CheckInit` is satisfied and the latch is
set. Zero means the window could not serve a provider and the caller should retry on a later one
— hence the second, idempotent call site after `window.show()`, which covers `--minimised` (no
splash was ever shown). Measured: warming on the splash succeeds, so in practice the fallback is
a no-op and **only the throwaway splash ever receives the synthetic message**. The Dashboard's
UIA provider is still built solely from real client requests.

Warm on the splash, never the Dashboard: the splash's accessible tree is two nodes, the
Dashboard's spans ~60 pages.

### Why not the other candidates

`UiaHostProviderFromHwnd`, `UiaGetReservedNotSupportedValue` and `UiaClientsAreListening` were
each tried as "cleaner" warmups that don't synthesise a client message. **All three leave the
fault firing** — measured. `CheckInit` lives specifically inside `UiaReturnRawElementProvider`,
and only a real `WM_GETOBJECT` round-trip through Qt reaches it.

### The near-miss worth remembering

The first version of the end-to-end test asserted only "the crash log did not grow". It passed.
It would also have passed on a warmup that silenced the fault while **poisoning the UIA
provider**, leaving the app completely undriveable by the monkey harness — a far worse
regression than the bug. The test now also asserts the UIA client can still read the window.

(The scare that surfaced this — `EVENT_E_ALL_SUBSCRIBERS_FAILED` on `top_window().descendants()`
— turned out to be **pre-existing** and unrelated: it reproduces identically on unmodified HEAD.
A bare `descendants()` walk of this ~60-page app is simply unreliable. The harness resolves its
window by a PID-filtered Desktop scan instead.)

---

## Not a crash, and not only a test-harness problem

Two things worth stating plainly, because both were misreported in earlier write-ups:

- **The app never crashed from this.** `startup-com-reentrancy.md` said "the process is simply
  gone"; that was wrong. It is a first-chance, handled exception. The apparent process deaths in
  the 2026-07-08 soak were the harness's own health-monitor `taskkill`-ing a stalled app.
- **It is not only the harness.** Narrator and NVDA are UIA clients and trip the identical path.
  The warmup is a real accessibility fix, which matters for Microsoft Store submission — that is
  why it ships unconditionally rather than gated behind a test-only env var.

---

## Side findings (fixed alongside)

Both in `ui/header.py`, both stale/false, both corrected in this change:

- `_install_window_chrome`'s docstring claimed the chrome "MUST run before any geometry is
  applied — `Dashboard.__init__` calls it ahead of `_restore_settings()`". `Dashboard.__init__`
  **does not call it at all**; `showEvent` is the only install site, which is necessarily *after*
  geometry restore. The code already compensates via `reapply_geometry_after_chrome()` (commit
  4c4043e) — the docstring now describes that instead of the imaginary ordering.
- The same docstring cited
  `tests/test_native_chrome.py::test_chrome_is_installed_before_geometry_is_restored` as its
  guard. **That test does not exist.**

One more, not fixed (no behavioural impact, and startup is delicate — RULE-STARTUP1): the
`process_events=False` argument to `_splash_msg()` is a no-op. `QSplashScreen::setPixmap` pumps
the event loop internally regardless (visible in the native stack above), so the flag cannot
suppress what it claims to suppress.
