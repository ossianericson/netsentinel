# NetSentinel Backlog

## Vision

NetSentinel has two parallel strategic goals: become the first tool recommended when anyone says "my network is broken" — the de-facto standard for home network troubleshooting — and become the natural starting point for anyone learning how networks actually work. Both goals are served by the same core property: the tool must show you what is happening on your real network, in plain English, without requiring you to already know what you are looking for. Everything on this backlog either lowers the barrier to non-technical users or makes the tool usable in structured learning contexts.

---

## Priority 1 — De-facto Home Standard

Items in this track lower the barrier for non-technical users. Each item should be self-contained, require no configuration, and produce output that a non-technical person can act on immediately.

---

### 4. Anonymous opt-in ISP comparison

**Description:** Opt-in only, zero PII. On opt-in, submits: ISP name, country code, anonymised speed, latency, and uptime percentage once per day. Shows the user how their connection compares to the median for their ISP and country. Requires explicit opt-in toggle with a clear sentence describing what is sent.

**Why it matters:** Contextualises results. "Your latency is 42 ms" is not actionable. "Your latency is 42 ms — 38% worse than the median for your ISP in your country" is. It also creates a daily re-engagement hook and produces community data that benefits all users.

**Effort:** L

**Files likely affected:**
- `modules/isp_telemetry.py` — new module, submission and query logic; must be opt-in only with no fallback to passive collection
- `ui/pages/speed_test_page.py` — opt-in toggle and comparison panel
- Requires a backend endpoint — document the API contract here before implementation

---

## Priority 2 — Educational Standard

Items in this track make NetSentinel usable in structured learning contexts. Each item should produce output that maps directly to a textbook concept or exam objective and can be submitted as evidence of work.

---

### 2. "What just happened?" contextual explanations

**Description:** After every scan, every BPDU detection, every CVE match, every alert — a collapsible panel at the bottom of the relevant page shows a plain-English explanation of the protocol involved and why the specific result matters. Collapsed by default to avoid obstructing experienced users.

**Why it matters:** Passive learning with zero extra effort from the user. A student who opens the Rogue Bridge tab and sees a rogue bridge detected also sees an explanation of what STP is, what a root bridge election does, and why this causes periodic drops — without navigating away from the result.

**Effort:** M

**Files likely affected:**
- `ui/widgets/explainer_panel.py` — new reusable widget, collapsible with a toggle chevron
- All detection page files — add the explainer panel to each relevant result area

---

### 3. CompTIA Network+ / CCNA curriculum alignment

**Description:** Each feature page shows which exam objective(s) it covers as a compact badge below the page title. An exportable "study session" report lists every feature used during the session alongside the corresponding exam objectives — formatted as a checklist a student can attach to homework or submit to an instructor.

**Why it matters:** Formal adoption by instructors requires curriculum mapping. Without it, a teacher cannot justify replacing a textbook lab with a live scan. With it, the tool becomes a natural fit for any course that covers CompTIA Network+ Domain 2 (Network Implementations) or CCNA Exam Topics 1.x–3.x.

**Effort:** S

**Files likely affected:**
- `data/curriculum_map.json` — new file, objective ID → feature mapping
- All `ui/pages/` files — read the map and render objective badges near page titles
- `ui/widgets/objective_badge.py` — new widget, renders a compact labelled badge

---

### 4. Classroom export

**Description:** Students export a signed scan report (JSON + rendered HTML) containing a timestamp, a machine fingerprint (non-identifying hash), scan results, and a list of features used. Instructors have a separate aggregation view: import multiple student reports and get a comparison table showing what each student found.

**Why it matters:** Makes the tool usable as a lab submission format. Without a way for instructors to collect and compare student results, individual exports are useful only to the student who ran them. With classroom export, a teacher can set "run a full scan and submit your report" as a graded lab.

**Effort:** M

**Files likely affected:**
- `modules/classroom_export.py` — new module, report signing and aggregation
- `ui/pages/classroom_page.py` — new page, student export view and teacher aggregation view

---

## Priority 3 — Polish and Retention

Items ordered by visual impact. Each is self-contained and can be implemented independently.

### Tier 2 — Structural polish

- **Skeleton loading rows while scan workers are running** — prevents layout jump when data arrives; use a `QStandardItemModel` with placeholder rows styled in `TEXT_MUTED`, swapped out when the worker emits results.

### Tier 4 — Nice-to-have

- **"Abyss" WCAG AA high-contrast theme** — fourth theme; true black background, high-contrast text, no low-opacity elements. Required for users with visual impairments.
- **Keyboard shortcut reference card in Help panel** — currently the shortcut list only appears in Settings.
- **Per-page documentation link** — small `?` link on each page header opening the relevant wiki section.
- **Passive 802.11 monitor mode capture** — optional advanced capture path that puts a supported NIC into monitor mode (via Npcap on Windows) and reads raw 802.11 management/probe/beacon frames, bypassing normal Ethernet capture. Primarily useful on networks with AP client isolation. Silently falls back to standard capture if unsupported. Pro-tier feature — too advanced and too NIC-dependent to be a home-user default.
