# APEX — Design System, Brand, Widget Specs

Spec §39 deliverables 2, 3, 4. Token values live in
[`shared/design-tokens/tokens.json`](../shared/design-tokens/tokens.json). This document says how to use them.

---

## 0. F1 broadcast restyle (current look)

The web preview, the **desktop widgets** and the Windows widget cards now use the language of F1 broadcast graphics.
iOS and Android still use the original APEX look below; porting them is the next design task.

- **Carbon and F1 red.** Carbon black `#15151E` with a faint diagonal weave, and F1 red `#E10600` for live, the speed
  line along the top edge, slanted tabs and the favourite highlight. Team colors appear as slanted stripes.
- **Type.** The official *Formula1 Display* is proprietary, so it isn't bundled. If it's installed on the machine,
  widgets use it automatically; otherwise **Titillium Web** (OFL, `backend/apex/preview/fonts`). Heavy (900) uppercase
  for names and numbers. Titillium's digits are tabular, so countdowns don't jitter.
- **Slanted tabs** (F1 TV lower-thirds) label every widget: `NEXT`, `● LIVE · RACE`, `LIGHTS OUT IN`, `WDC`.
- **Countdowns in boxes** (F1.com style): `DAYS HRS MINS SECS`.
- **Timing tower** rows: position chip (white for the podium), slanted team stripe, three-letter code, gap.
- **Driver card:** the favourite driver's official F1 headshot in full colour, fading out behind their helmet, which
  glows in the team color (served by `/api/drivers/{id}/silhouette.png`; drivers without a helmet render get the
  face alone), in front of their race number, giant and outlined.
- **Windows cards** can't load fonts or colors (the board owns them), so they get the portrait and race number,
  uppercase labels and semantic red for live; the type stays Segoe UI.

The renderer is shared: `backend/apex/preview/widgets.css` + `widgets.js`, used by `index.html` (preview) and
`desktop.html` (one desktop widget per window).

## 1. Brand

**APEX** is the point where a car is closest to the inside of a corner. It's the moment of precision, and
what the product does with information: shortest line to the answer.

| Asset | File | Use |
|---|---|---|
| Mark | `shared/brand/apex-mark.svg` | App icon, widget corner, favicon. Built on a 24 px grid, still legible at 16 px |
| Mark, mono | `shared/brand/apex-mark-mono.svg` | Lock screen, monochrome tints, Windows tray (`currentColor`) |
| Wordmark | `shared/brand/apex-wordmark.svg` | Companion app header, store listing |
| App icon | `shared/brand/apex-app-icon.svg` | 1024² full bleed; platforms apply their own mask |

**The mark.** A chevron *A* is the corner, and the crossbar is the racing line, drawn as a rising
diagonal in Signal that clips the apex and exits past the right leg. It uses straight strokes with square caps
and miter joins, and no curves except in the P of the wordmark. In monochrome the racing line becomes the same ink as
the chevron, and the gesture still reads.

**Don't:** put the mark in a circle, add a gradient, or set the wordmark in a font. The letters are
drawn paths so they always match the mark's stroke.

---

## 2. Color

Dark-first, with three themes: Dark, AMOLED and Light. Grey does the work. **Signal** (`#FF5A1F`) is the one accent:
a warm orange-red that reads as motorsport without becoming the brand color.

Signal is allowed for exactly these things (spec §2):
1. The live dot and the `LIVE` label
2. The apex rail while a session is live
3. The selected or favourite driver highlight (a 2px leading bar, never a filled row)
4. Selected state in the companion app
5. Notification badge

Everything else is greyscale. That includes position numbers, timing, borders and headers.

**Team color** appears only as a 2px vertical tick before a driver code or team name, and only when
"Show team colors" is on. Team colors come from the API (OpenF1 `team_colour`), never from client
code. In AMOLED and Light themes the tick has a 1px `border` outline so pale team colors (Haas grey,
Mercedes teal on white) stay visible.

**Sector colors** keep the timing-screen convention (purple = overall best, green = personal
best, yellow = no improvement), and each carries a glyph (◆ ▲ –) so the meaning survives
color-blindness and greyscale (spec §28).

---

## 3. Typography

| Role | Token | Font | Example |
|---|---|---|---|
| Hero number | `hero` 44/600, −1.5 | Mono | `02:14:32` |
| Display | `display` 32/600, −1 | Mono | `P3` |
| Title | `title` 17/600 | Sans | `Singapore GP` (rare: only the app) |
| Body | `body` 14/500 | Sans | settings rows |
| Data | `data` 13/500 | Mono | `1  ANT  1:38.589` |
| Meta | `meta` 11/600, +0.8, UPPER | Sans | `QUALIFYING · SAT 21:00` |
| Micro | `micro` 9/600, +0.8, UPPER | Sans | `LAST UPDATED 2M AGO` |

- **Numbers are always tabular**, so digits never jitter when a countdown ticks.
- The web reference uses Geist and Geist Mono. iOS uses SF Pro with `.monospacedDigit()` for numbers and SF Mono
  for timing tables. Android widgets use the system sans and monospace (Glance can't load custom fonts).
  Windows follows its own widget type ramp (Segoe UI), whose digits are already tabular, so it feels native
  (spec §5).
- Widget text never goes below 11 pt except `micro` (9) on small widgets, and every size scales
  with Dynamic Type / font scale up to accessibility sizes. Layouts collapse to fewer rows
  instead of truncating codes.

---

## 4. Space, shape, depth

- **8px grid.** Widget padding is 16 (`l`), group gap 12 (`m`), row gap 4 (`xs`). Data rows are 18 px high
  at default type size.
- **Radii are small:** 2 (ticks, rail), 4 (chips), 8 (app panels). The widget container radius
  belongs to the platform (iOS ~22, Android launcher-defined, Windows 8). We never fight it.
- **1px hairline borders** in `border`. Depth comes from the surface steps
  (background → surface → elevated), not shadows. `shadow.soft` is only for floating app sheets.
- **Whitespace is a feature.** A small widget shows one number. If a layout fills every pixel, a row
  gets cut.

---

## 5. The apex rail

The one memorable element. It's a 2px line along the bottom inside edge of a widget, and its fill
shows progress through the current thing:

| Context | Fill = |
|---|---|
| Countdown | time elapsed since the previous session ended ÷ time until this one starts |
| Live race | lap / laps_total, filled in Signal |
| Live quali/practice | elapsed / scheduled session duration, in Signal |
| Results / next / standings | not shown |

It replaces a progress bar, percentages and lap counters in widgets too small for text.

---

## 6. Status language

| State | Glyph | Text | Color |
|---|---|---|---|
| Live | `●` (2 s opacity pulse 1 → 0.45; static with Reduce Motion) | `LIVE` | Signal |
| Starting soon | `◐` | `SOON` | primary |
| Upcoming | `○` | — | secondary |
| Finished | `✓` | — | secondary |
| Stale data | — | `LAST UPDATED 2M AGO` | tertiary |
| Live unavailable | — | `LIVE DATA UNAVAILABLE` | secondary + Signal dot (no pulse) |

The pulse is the only ambient animation in the product.

---

## 7. Motion

Motion explains a change. It never decorates.

| Event | Motion |
|---|---|
| Position change `P4 → P3` | Row slides one row height, spring (0.35 s, damping 0.86); the code briefly holds `textPrimary` weight 700 |
| Countdown → LIVE | Digits crossfade out (160 ms), `● LIVE` fades in, rail switches to Signal |
| Driver pits | Gap value is replaced by `PIT` with a vertical push transition |
| Number updates | `contentTransition(.numericText())` (iOS), animated text (Compose), crossfade (Windows) |
| Reduce Motion | All of the above become opacity crossfades; the pulse stops |

No particles, bounces, glows or neon.

---

## 8. Widget specifications

Each widget answers one question in under 2 seconds. Hierarchy: **live status → session →
the number → context → secondary**. Sizes get distinct layouts, never a scaled one.

Platform size map: **S** = iOS small / Android 2×2 / Windows small. **M** = iOS medium / Android 4×2 /
Windows medium. **L** = iOS large / Android 4×4 / Windows large. **Lock** = iOS accessoryRectangular,
accessoryCircular and accessoryInline.

### 8.1 Race Mode (“APEX”, the default widget)
Shows whichever widget below fits right now: LIVE → Live Timing, RESULTS → final classification,
COUNTDOWN → Countdown, NEXT → Next Session. Most users only ever add this one.

### 8.2 Next Session — *What's next and when?*
```text
S                      M                                   L
┌──────────────┐       ┌──────────────────────────────────┐  M + full weekend list (8.6)
│ SG  SINGAPORE│       │ SG  SINGAPORE GP           R17   │
│              │       │                                  │
│ QUALIFYING   │       │ QUALIFYING           STARTS IN   │
│ SAT · 21:00  │       │ SAT · 21:00          02:14:32    │
│     02:14:32 │       │ ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔ rail ▔▔▔ │
└──────────────┘       └──────────────────────────────────┘
```
States: upcoming, starting soon (`◐ SOON`, countdown in primary weight 700), live (switches to
`● LIVE` with the session name; tapping opens Live Timing), finished (rolls to the next session).

### 8.3 Countdown — *How long until the race?*
```text
S                 M                                     Lock (rectangular)
┌─────────────┐   ┌───────────────────────────────────┐  RACE · SINGAPORE
│ RACE IN     │   │ RACE STARTS IN        SINGAPORE GP │  01d 04:32:18
│ 01 DAYS     │   │ 01      04:32:18                   │
│ 04:32:18    │   │ DAYS    HRS MIN SEC    SUN · 20:00 │
└─────────────┘   └───────────────────────────────────┘
```
Under 24 h, the days line is removed and `HH:MM:SS` grows to `hero`. Timelines tick with
`Text(timerInterval:)` (iOS), `Chronometer` (Android) or a 1-minute card refresh (Windows), and
switch to LIVE at the start entry without a network call.

### 8.4 Live Timing — *Who's leading and by how much?*
```text
S                 M                                       L
┌─────────────┐   ┌─────────────────────────────────────┐  ┌──────────────────────────────┐
│ ● LIVE  L42 │   │ ● LIVE · RACE           L42 / 62    │  │ ● LIVE · RACE      L42 / 62   │
│             │   │ 1 ANT  LEADER      4 PIA  +6.821    │  │ SINGAPORE GP                  │
│ P1          │   │ 2 RUS  +1.821      5 LEC  +8.004    │  │ 1  ANT  ◆▲–   LEADER          │
│ ANT         │   │ 3 NOR  +4.209      6 HAM  PIT       │  │ 2  RUS  ▲▲–   +1.821          │
│ ▔▔▔▔▔▔▔▔▔▔  │   │ ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔ rail ▔▔▔▔▔ │  │ … 10 rows …                   │
└─────────────┘   └─────────────────────────────────────┘  └──────────────────────────────┘
```
Quali shows `● LIVE · Q3` and best times, with P1's lap in full and the rest as gaps. Race shows gap to
leader. Sector glyphs appear only on L (no room elsewhere). `PIT` replaces the gap. The favourite
driver gets a Signal leading bar, and if they're outside the visible rows, the last row becomes
`… 9 VER +21.4`.

### 8.5 Driver — *How is my driver doing this season?*
```text
M                                         L adds: WINS/PODIUMS/POLES row + LAST 5
┌───────────────────────────────────────┐
│ ▍KIMI ANTONELLI        IT  MERCEDES   │   LAST 5
│ P1                      320 PTS       │   P2 · P1 · P1 · P4 · P1
│ WINS 8   PODIUMS 12   POLES 6         │
└───────────────────────────────────────┘
```
Configurable: driver, season, which stats appear (App Intent / Glance config / Windows
customization). S shows `P1` / `ANT` / `320 PTS`.

### 8.6 Race Weekend — *Where are we in the weekend?*
```text
M/L only
SINGAPORE GP                    R17
FRI  FP1          ✓
FRI  SPRINT QUALI ✓
SAT  SPRINT       ●  LIVE
SAT  QUALIFYING   ○  13:00
SUN  RACE         ○  12:00
```
Glyphs carry the state. The live row is primary weight with Signal `●`. Finished rows are tertiary.

### 8.7 Championship (WDC / WCC) — *Who's winning the title?*
```text
M                          L: 10 rows + gap to leader column
WDC                 R16
01  ANT  320
02  RUS  298
03  NOR  271
```
WCC uses team names in 9 characters max (`RED BULL`, `MCLAREN`, `ASTON`) with a team tick. The
selected driver or team gets the Signal bar. If they're outside the top N, the last row is replaced with
`… 07 HAM 121`.

### 8.8 Favourite Driver (smart) — *What matters about my driver right now?*
| Moment | S shows |
|---|---|
| Live session | `P3` / `L42` / `+4.821` (or `PIT`) |
| After race | `P2` / `+8.221` |
| After quali, before race | `QUALI P3` / race countdown |
| Otherwise | championship `P1` / `320 PTS` |

### 8.9 Empty, error and loading
- **No live session:** `NO LIVE SESSION` → next session name, day/time and countdown (spec §33).
- **Stale:** the widget shows the cached snapshot plus `LAST UPDATED 2M AGO` in `micro`. A widget is never blank.
- **Live unavailable:** `LIVE DATA UNAVAILABLE` / `Using cached data` / `Updated 42s ago` / a **Retry**
  control (app intent / Glance action / card action). Never a stack trace.
- **Loading:** skeleton bars with the exact geometry of the real rows, filled with `elevated`. There are
  no spinners anywhere.

---

## 9. Platform adaptation

| | iOS | Android | Windows |
|---|---|---|---|
| Surface | `containerBackground` in `surface`, system corner radius | APEX palette, honors launcher radius via `cornerRadius(android:dimen/system_app_widget_background_radius)` | Widget Board card with Adaptive Card templates; background and colors come from the system theme |
| Type | SF Pro + monospaced digits | System sans + monospace | Segoe UI type ramp (tabular digits) |
| Countdown ticking | `Text(timerInterval:)` | platform `Chronometer` via `AndroidRemoteViews` | provider pushes once a second while the board is open |
| Config | App Intents (`WidgetConfigurationIntent`), plus app defaults | Companion app settings (shared by all widgets), "Add to home screen" pinning | Per-widget customization card on the board (`OnCustomizationRequested`), plus app defaults |
| Live | Live Activity + Dynamic Island | opt-in ongoing progress notification, 1-minute refresh | 30-second fetch while the board is open |
| Color | `widgetRenderingMode` accented/vibrant: drop team ticks, keep glyphs | Signal + team ticks | semantic only: live = `Attention`, no team ticks (Adaptive Cards have no hex colors); glyphs carry state |

---

## 10. Final design test (spec §40) checklist

Run before shipping any widget change:

- [ ] Can someone read the F1 situation in 2 seconds? (Squint test at arm's length.)
- [ ] Does it hold up at the smallest size and the largest font scale?
- [ ] Does it hold up in greyscale? (Every status has a glyph.)
- [ ] Does it look the same in spirit on iOS, Android and Windows, but native on each?
- [ ] Is it useful without opening the app?
- [ ] Does it update itself at session boundaries?
- [ ] Does anything look like a template? If yes, remove it.
