---
applyTo: "**"
---

# NetSentinel — Enterprise UI Design System

## Governing Principle

The UI must follow a **"minimalist approach to a maximalist solution"** — eliminate decorative noise so the user's focus stays on the data. Every screen must feel like a professional network monitoring console used by IT engineers, not a consumer app. Information density is a feature, not a problem.

---

## 1. Application Shell Structure

### 1.1 Top Application Bar
- Fixed height: **42px**
- Background: **`#141B2D`** (near-black navy)
- Left zone: product name/logo in white, bold, 14px
- Centre zone: primary navigation items — flat text links, no underline, white at 12px, spaced 24px apart. Items: "My Dashboards", "Alerts & Activity", "Reports", "Settings"
- Right zone: notification bell icon (with red badge count), search icon, user account label + logout
- No border-bottom decoration — the contrast between the bar and content below is sufficient
- This bar is **always visible**, never hidden, never collapsed

### 1.2 Content Area
- Background: **`#F4F4F4`** (light off-white) — not pure white, not grey
- Content begins immediately below the top bar (no secondary toolbar)
- Page title appears as the first element on each page: left-aligned, 18px bold, `#1A1A2E`, with optional subtitle in 12px `#5A6A7A` below it
- Optional thin breadcrumb trail (`Home › Section › Page`) at 11px below page title

### 1.3 Sidebar (Left Navigation)
- Width: **220px** fixed
- Background: **`#1F2B3E`** (dark navy-charcoal)
- Navigation items: 30px tall, 12px Segoe UI, color `#A8B8C8`
- Active item: left border accent **3px solid `#0078D4`**, background `#243348`, text white, bold
- Hover item: background `#2A3A52`, text white
- Section headers: ALL CAPS, 9px, `#6A8099`, 28px tall rows, non-clickable, background `#172333` — visually group items below
- Sections present: STANDARD (always visible), ADVANCED (toggle-revealed), SECURITY AUDIT (toggle-revealed)
- No icons with colour fills — sidebar items are text-only or use minimal outline symbols
- A 1px `#0A0E1A` vertical divider separates the sidebar from the content area

---

## 2. Card / Widget System

### 2.1 Card Anatomy
Every data section must be wrapped in a **card widget**. A card consists of:

```
┌─────────────────────────────────────────────┐
│ TITLE BAR  (white, 32px tall)               │
│  [Bold title 13px #1A1A2E]      [EDIT HELP] │
├─────────────────────────────────────────────┤
│                                             │
│  Card body — table, chart, or form          │
│  Background: #FFFFFF                        │
│                                             │
└─────────────────────────────────────────────┘
```

- **Card border**: `1px solid #D4D4D4`, border-radius `0px` (sharp corners, enterprise look)
- **Card background**: `#FFFFFF`
- **Title bar**: white background, title text bold 13px `#1A1A2E`, action links ("EDIT", "HELP") right-aligned at 11px `#0078D4`
- **Title bar bottom border**: `1px solid #ECECEC`
- **Card body padding**: 0px for tables (table fills edge to edge), 12px for text/chart content
- Cards arrange in a **multi-column grid** (2 or 3 equal-width columns) using horizontal `QHBoxLayout` with `QSplitter` between them

### 2.2 Card Grid Layout
- Dashboards show 2–3 cards per row
- Cards in the same row share equal width
- Vertical spacing between rows: 10px
- Cards containing tables fill their available height; cards containing charts have a fixed minimum height of 200px

---

## 3. Data Tables

### 3.1 Table Structure
- No border-radius — tables are rectangular
- **Header row**: background `#1A3A5C`, text `#FFFFFF`, 11px bold uppercase, letter-spacing 0.5px
- **Column padding**: 5px left/right, 4px top/bottom
- **Zebra striping**: odd rows `#FFFFFF`, even rows `#F7F9FC`
- **Row hover**: `#EEF4FF` (light blue tint)
- **Selected row**: `#CCE4F7` with `#1A1A2E` text (never invert to white-on-dark)
- **Grid lines**: `1px solid #EAEAEA` horizontal only — NO vertical grid lines inside the body
- **Row height**: 24px compact — this is non-negotiable for information density
- **Font**: 11px Segoe UI, `#1A1A2E`

### 3.2 Status Indicators in Tables
Status is always shown as a **small filled circle** (12px diameter) to the left of the item name:
- 🟢 `#2E7D32` — Up / Clean / Safe
- 🟡 `#F59E0B` — Warning / Degraded
- 🔴 `#D93025` — Critical / Down / Rogue
- ⚫ `#9BA8B4` — Unknown / Unreachable

Never use text alone for status. The circle icon must appear with (or instead of) text.

### 3.3 Hyperlinks in Tables
Device names, IP addresses, and hostnames that are actionable must appear as `#0078D4` blue hyperlinks (underline on hover only). This signals the user can click for drill-down detail.

### 3.4 In-Cell Progress Bars
For percentage columns (utilisation, packet loss, signal strength): render a **horizontal fill bar** inside the cell — a thin 6px-height bar behind the percentage text. Fill colour:
- 0–60%: `#2E7D32` (green)
- 61–80%: `#F59E0B` (amber)
- 81–100%: `#D93025` (red)

---

## 4. Charts and Graphs

### 4.1 Area / Line Charts
All time-series charts use matplotlib embedded via `FigureCanvas`. Rules:

- **Canvas background**: `#FFFFFF`
- **Plot area background**: `#FAFBFC`
- **Grid lines**: `#E8EDF2`, horizontal only, linewidth 0.8, solid
- **Axis spines**: show only bottom and left, color `#D4D4D4`. Hide top and right.
- **Axis tick labels**: 9px, `#5A6A7A`
- **Axis titles**: 9px, `#5A6A7A`
- **Chart title**: 11px bold, `#1A3A5C`, shown above the plot area

#### Area chart fill colours (stacked):
```
Series 1: #0078D4 (brand blue)   fill alpha 0.7
Series 2: #2E7D32 (green)        fill alpha 0.6
Series 3: #F59E0B (amber/gold)   fill alpha 0.5
Series 4: #5A6A7A (slate)        fill alpha 0.4
```

- Line weight: 1.5px
- No markers on line chart points
- Timeout/drop events: red `×` scatter marker at y=0

#### Zoom controls
Above every time-series chart, render small flat buttons: **"1h"  "12h"  "24h"** — these filter the visible time window. Style: 11px, `#0078D4`, `1px solid #B0C4D8` border, `#FFFFFF` background, active state: `#0078D4` fill with white text.

#### Legend
- Positioned below the chart (not inside it)
- Small 10×10px filled squares followed by label text at 9px `#5A6A7A`
- Legend background: `#FFFFFF`, border: `1px solid #D4D4D4`

### 4.2 Radial / Gauge Charts
For single-value KPI widgets (e.g., "Current Duration", "Health Score"):
- Dark circular gauge with tick marks
- Large number in centre: 28px bold `#1A1A2E`
- Label below number: 11px `#5A6A7A`
- Needle or arc fill coloured by threshold (green/amber/red)

### 4.3 Pie / Donut Charts
- White background
- Segments: use status colours (green=up, amber=warning, red=critical, grey=unknown)
- Centre label (for donut): large number + small unit text
- No 3D effects, no shadows
- Legend to the right of the chart in a table: colour square + label + count

---

## 5. KPI Stat Cards

For summary numbers shown inline (e.g., "Total Devices: 42", "Avg RTT: 14ms"):

```
┌──────────────────────┐
│ LABEL (9px, grey)    │  ← uppercase micro-label
│ 42  (22px, bold)     │  ← large number
└──────────────────────┘
```

- Card: `#FFFFFF` background, `1px solid #D4D4D4` border, `3px solid #0078D4` left border accent
- Multiple KPI cards appear side-by-side in a horizontal row above the main table
- Width: auto (fit content), minimum 100px each

---

## 6. Network Topology View

### 6.1 Canvas
- White `#FFFFFF` background
- Matplotlib `ax.axis("off")` — no axis lines
- Light `#E8EDF2` background for the figure itself

### 6.2 Nodes
- Circular nodes, hollow (white fill, coloured stroke ring):
  - `3px` stroke, color = device status (green/amber/red/grey from section 3.2)
- Node size: proportional to importance (gateway larger than leaf devices)
- Node label: device name top, IP address bottom, 8px `#1A1A2E`, white bbox with `#D4D4D4` border
- Selected/highlighted node: light blue `#CCE4F7` highlight box behind it

### 6.3 Edges (links)
- Color: `#B0BEC8` for normal links
- Color: `#D93025` for links with detected issues
- Width: 1.5px for primary path, 1.0px for secondary
- Edge label (latency): small text "19ms" at midpoint, 8px `#5A6A7A`, no background

### 6.4 Detail Side Panel
When a node is selected, a right-side detail panel slides/appears:
- Width: ~280px
- Background: `#FFFFFF`, left border `3px solid #D4D4D4`
- Shows: node name (bold 13px), IP, vendor, status badge
- Issues section: red `!` badge with count, then bulleted issue list
- Metrics: Latency (min/avg/max in a 3-column mini-table), Packet Loss %

### 6.5 Path History Strip
At the bottom of the topology view, a thin **availability timeline strip**:
- Height: 16px
- Each pixel-width segment coloured: green=up, red=down, amber=degraded
- Time labels below: left = start time, right = current time
- Zoom buttons: "Last 1 hour", "Last 24 hours"

---

## 7. Buttons

| Type | Style |
|---|---|
| Primary action (Run Scan) | `#0078D4` fill, white text, 4px radius, 34px height, 12px bold |
| Secondary (Export, Refresh) | White fill, `1px solid #0078D4` border, `#0078D4` text, 4px radius |
| Destructive / Alert action | `#D93025` fill, white text |
| Toggle (on) | `#0078D4` fill, white text |
| Toggle (off) | `#FFFFFF` fill, `1px solid #B0C4D8` border, `#5A6A7A` text |
| Disabled | `#B0C4D8` fill or border, `#9BA8B4` text |
| Inline link button | No border, no background, `#0078D4` text, underline on hover |

- No gradients
- No glow/shadow effects
- No border-radius > 4px

---

## 8. Alerts & Notification System

### 8.1 Global Notification Bar (Admin Warning / System Alerts)
- **Height: 28px maximum** — thin horizontal strip pinned just below the top bar
- Background: `#FFF3CD`, bottom border `1px solid #F0A500`
- Warning icon `⚠` (12px, `#92600A`) + message text (11px, `#92600A`) + dismiss `✕` button right-aligned
- **Never** use a large block/card for a warning — this wastes screen real estate

### 8.2 In-Table Alert Badges
For severity counts in summary rows: small rectangular badges with number inside
- Critical: `#D93025` background, white text
- Warning: `#F59E0B` background, white text
- Info: `#0078D4` background, white text

### 8.3 Verdict / Result Panel
- Thin horizontal bar at bottom of the main content area
- Left border accent colour = result severity
- Shows: severity icon + one-line plain-English summary
- Max height 80px — does not dominate the screen

---

## 9. Typography

| Usage | Font | Size | Weight | Color |
|---|---|---|---|---|
| Page title | Segoe UI | 18px | Bold | `#1A1A2E` |
| Card/widget title | Segoe UI | 13px | Bold | `#1A1A2E` |
| Table header | Segoe UI | 11px | Bold | `#FFFFFF` |
| Table data | Segoe UI | 11px | Regular | `#1A1A2E` |
| Label / secondary | Segoe UI | 11px | Regular | `#5A6A7A` |
| Micro-label (KPI) | Segoe UI | 9px | Bold | `#5A6A7A` |
| Sidebar nav | Segoe UI | 12px | Regular | `#A8B8C8` |
| Breadcrumb | Segoe UI | 11px | Regular | `#5A6A7A` |
| Status bar | Segoe UI | 11px | Regular | `#9DB0C4` |

**No font size above 18px anywhere in the application** (except the centre number in gauge widgets).

---

## 10. Interaction & Behaviour Rules

1. **Right-click context menu** on any table row must offer: "Copy IP", "Copy MAC", "Copy Row", relevant actions (Port Scan, Wake-on-LAN, How to Fix)
2. **Context menus**: white background `#FFFFFF`, `1px solid #D4D4D4` border, 11px text, hover = `#EEF4FF` row
3. **Column sorting**: clicking a column header sorts — show a small ▲/▼ indicator in the header
4. **Hover tooltip**: dark `#1A3A5C` background, white text, 3px radius, appears within 400ms
5. **Loading state**: thin 4px indeterminate progress bar at the very top of the content area (not a spinner overlay blocking the UI)
6. **Empty state**: centred placeholder text in `#9BA8B4` with a suggestion ("Run a scan to populate this table") — never leave a blank white box

---

## 11. What is Explicitly Forbidden

- ❌ Dark/black backgrounds for content areas or tables
- ❌ Neon, purple, or saturated colours in the content area
- ❌ Rounded corners > 4px on cards or tables
- ❌ Gradient fills on buttons
- ❌ Glow effects, drop shadows on data elements
- ❌ Font sizes above 18px in data views
- ❌ Full-screen modal overlays for warnings (use the thin notification bar)
- ❌ Animations that delay data presentation
- ❌ Emojis as primary status indicators (use coloured circles instead; emojis may appear in navigation labels only)
- ❌ Tabs (`QTabWidget`) as the primary navigation — use the sidebar + stacked pages pattern
