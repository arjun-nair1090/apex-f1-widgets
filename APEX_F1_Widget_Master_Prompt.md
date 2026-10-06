# F1 Widget — Cross-Platform Motorsport Widget Ecosystem

## ROLE

You are a world-class product designer, UI/UX designer, frontend engineer, mobile engineer, and systems architect.

Build a premium cross-platform F1 widget ecosystem inspired by the best parts of modern motorsport apps, but with an original identity.

The product's primary purpose is **not** to be a traditional F1 app.

The product is:

> **A beautiful, minimal, real-time F1 information system that lives on the user's home screen, lock screen, desktop, and widgets.**

The widgets are the product.

Do not build a generic dashboard and call it a widget app. Design the entire experience around glanceable information.

---

# 1. PRODUCT VISION

The application should feel like a premium motorsport product created by a company such as:

- Apple
- Porsche
- Formula 1
- Nothing
- Linear
- Arc
- Garmin

The UI should feel:

- Premium
- Fast
- Technical
- Minimal
- Motorsport-focused
- Modern
- Dark
- Extremely polished
- Information-dense without feeling cluttered

Avoid:

- Generic dashboard layouts
- Excessive cards
- Huge gradients
- Neon gaming aesthetics
- Excessive red
- Generic Bootstrap styling
- Template-like interfaces
- Excessive rounded corners
- Unnecessary animations
- Clutter

The visual language should communicate:

**speed + precision + telemetry + engineering + premium motorsport**

---

# 2. BRANDING

Create an original brand identity.

Do **not** copy Box Box Club's branding, layouts, logos, typography, or exact visual design.

Use a placeholder brand name:

**APEX**

The product should feel like:

> "The F1 data layer that lives everywhere."

Create a simple wordmark/logo system for APEX.

Logo concept:

- Minimal
- Geometric
- Motorsport-inspired
- Works at 16px
- Works as an app icon
- Works in monochrome

Primary theme:

Dark-first.

Suggested palette:

- Background: `#08090B`
- Surface: `#111318`
- Elevated surface: `#181B21`
- Primary text: `#F5F7FA`
- Secondary text: `#9298A3`
- Accent: restrained motorsport red/orange

Do not make the entire application red.

Use accent colors primarily for:

- Live status
- Important telemetry
- Selected states
- Session indicators
- Notifications

Allow team colors to appear only where contextually appropriate.

---

# 3. TYPOGRAPHY

Typography is extremely important.

Use a modern geometric/sans-serif font.

Prioritize:

- Inter
- Geist
- SF Pro equivalent
- Manrope

For telemetry/numbers, use a monospace or tabular-number font.

Numbers should feel like:

- race timing displays
- telemetry
- pit wall timing screens

Examples:

```text
01:24.382
+1.824
LAP 42/58
P1
312 PTS
```

Use:

- Tight typography
- Strong hierarchy
- Tabular numbers
- Large numerical information
- Small uppercase metadata

Avoid excessive text.

---

# 4. CORE UX PRINCIPLE

Every widget must answer:

> "What does the user need to know in under 2 seconds?"

Information hierarchy:

1. Live status
2. Current session
3. Important number
4. Context
5. Secondary information

Example:

### Bad

```text
Formula 1 Singapore Grand Prix Race
```

### Good

```text
🔴 LIVE
SINGAPORE GP
L42 / 62
```

---

# 5. PLATFORM SUPPORT

The system must support:

## iOS

Use:

- SwiftUI
- WidgetKit
- App Intents
- Live Activities where appropriate
- Dynamic Island where supported
- Lock Screen widgets
- Home Screen widgets

Widget sizes:

- Small
- Medium
- Large
- Lock Screen

## Android

Use:

- Kotlin
- Jetpack Glance where appropriate
- Android App Widgets
- Material 3
- Dynamic/responsive layouts

Support:

- Small
- Medium
- Large
- Resizable widgets

## Windows

Use:

- Windows App SDK / supported Windows Widgets architecture
- Native Windows design principles
- Desktop widget surfaces where supported

The Windows experience should feel native rather than like a web page inside a widget.

---

# 6. CROSS-PLATFORM DESIGN SYSTEM

Create **one design system**.

All platforms must visually belong to the same product.

However:

**Do not simply copy the iOS UI onto Android or Windows.**

Adapt each implementation to platform conventions.

Create shared design tokens for:

- Colors
- Typography
- Spacing
- Radius
- Shadows
- Icons
- Motion
- Data formatting
- Status indicators

---

# 7. CORE WIDGETS

Build the following widgets.

## Widget 1 — NEXT SESSION

Example:

```text
┌──────────────────────────────┐
│ 🇸🇬  SINGAPORE GP             │
│                              │
│ QUALIFYING                   │
│ SAT · 21:00                  │
│                              │
│ STARTS IN                    │
│ 02:14:32                     │
└──────────────────────────────┘
```

The widget should automatically update based on the session schedule.

States:

- Upcoming
- Starting soon
- Live
- Finished

---

# 8. COUNTDOWN WIDGET

Large, beautiful countdown.

Example:

```text
RACE STARTS IN

01
DAYS

04:32:18
```

When the session begins:

**Switch automatically to LIVE.**

Do not require manual refresh.

---

# 9. LIVE TIMING WIDGET

This is one of the most important widgets.

Example:

```text
🔴 LIVE · Q3

1  VER   1:29.184
2  NOR   +0.082
3  LEC   +0.143
4  PIA   +0.304
5  HAM   +0.401
```

Show:

- Position
- Driver abbreviation
- Lap time/gap
- Sector status when available
- DRS status when available
- Pit status when available

Use subtle motion for position changes.

Never make the widget visually chaotic.

---

# 10. DRIVER WIDGET

Allow users to select their favourite driver.

Example:

```text
MAX VERSTAPPEN
🇳🇱 RED BULL RACING

P1
312 PTS

WINS 4
PODIUMS 9
POLES 3

LAST 5

P2 · P1 · P4 · P3 · P2
```

Users should be able to configure:

- Driver
- Season
- Information displayed

---

# 11. DRIVER CHAMPIONSHIP

Example:

```text
WDC

01  VER  312
02  NOR  298
03  LEC  271
04  PIA  249
05  HAM  221
```

Use very compact typography.

Highlight the user's selected driver.

---

# 12. CONSTRUCTOR CHAMPIONSHIP

Example:

```text
WCC

01  MCLAREN     547
02  FERRARI     492
03  RED BULL    461
```

Allow team colors to subtly appear as accents.

---

# 13. RACE WEEKEND WIDGET

Show the complete weekend.

Example:

```text
SINGAPORE GP

FRI
FP1       ✓

FRI
FP2       ✓

SAT
FP3       ●

SAT
QUALIFYING ○

SUN
RACE      ○
```

Use clear visual states:

- `✓` completed
- `●` live
- `○` upcoming

---

# 14. FAVOURITE DRIVER WIDGET

Users select their driver.

The widget should dynamically display the most useful information depending on the current session.

Before race:

```text
QUALI P3
```

During race:

```text
P3
L42
+4.821
```

After race:

```text
P2
+8.221
```

This widget should feel intelligent.

---

# 15. RACE MODE

Create an automatic **Race Mode**.

When a session is live:

The widget system should prioritize live information.

Before session:

**Countdown**

During session:

**Live timing**

After session:

**Results**

Between sessions:

**Next session**

This should happen automatically.

---

# 16. LIVE STATUS

Use a small but highly recognizable live indicator.

Example:

```text
● LIVE
```

The live indicator should have a very subtle pulse.

Do **not** use excessive flashing.

Accessibility must remain good.

---

# 17. APP EXPERIENCE

Even though widgets are the main product, create a small companion application.

The app should primarily handle:

- Widget configuration
- Favourite driver
- Favourite team
- Widget customization
- Notification settings
- Data source status
- Account/settings
- Previewing widgets

The app should **not** become a massive F1 news application.

Keep it focused.

---

# 18. WIDGET CUSTOMIZATION

Allow users to configure:

### Driver

- Verstappen
- Norris
- Leclerc
- Piastri
- Hamilton
- etc.

### Team

- McLaren
- Ferrari
- Red Bull
- Mercedes
- etc.

### Information density

- Minimal
- Standard
- Detailed

### Theme

- Dark
- AMOLED
- Light

### Accent

- System
- Team color
- Motorsport red

---

# 19. WIDGET PREVIEW SYSTEM

Create a beautiful widget customization screen.

Example:

```text
             YOUR WIDGET

        ┌────────────────────┐
        │ 🔴 LIVE            │
        │                    │
        │ SINGAPORE GP       │
        │ L42 / 62           │
        │                    │
        │ 1 VER  2 NOR       │
        │ 3 LEC  4 PIA       │
        └────────────────────┘
```

Below:

```text
Driver
[ MAX VERSTAPPEN ▼ ]

Style
[ Minimal ]

Information
[ Standard ]

Show Team Colors
[ ON ]
```

The preview should update immediately.

---

# 20. DATA ARCHITECTURE

Do **not** hardcode F1 data.

Create a backend API.

Recommended architecture:

- Backend: Python + FastAPI
- Database: PostgreSQL
- Cache: Redis
- Data ingestion: FastF1 and/or a reliable F1 timing/data provider

Architecture:

```text
F1 DATA
   ↓
DATA INGESTION
   ↓
NORMALIZATION
   ↓
POSTGRESQL
   ↓
REDIS CACHE
   ↓
FASTAPI
   ↓
iOS / Android / Windows
   ↓
WIDGETS
```

---

# 21. API

Create clean APIs such as:

```http
GET /api/season/current

GET /api/races

GET /api/races/{round}

GET /api/races/next

GET /api/session/next

GET /api/session/live

GET /api/session/{id}/timing

GET /api/standings/drivers

GET /api/standings/constructors

GET /api/drivers

GET /api/drivers/{id}

GET /api/teams

GET /api/teams/{id}

GET /api/status
```

Use proper schemas and validation.

---

# 22. REAL-TIME DATA

Live timing must not rely on repeatedly opening the entire app.

Use an efficient real-time architecture.

Possible architecture:

```text
F1 Data Provider
       ↓
Live Data Processor
       ↓
Redis
       ↓
WebSocket / SSE
       ↓
API
       ↓
Widgets
```

Implement intelligent caching.

Do not unnecessarily hammer the data source.

---

# 23. OFFLINE BEHAVIOR

Widgets must degrade gracefully.

If live data isn't available:

**Show the latest cached information.**

Example:

```text
LAST UPDATED
2m AGO
```

Never show an empty widget.

---

# 24. NOTIFICATIONS

Keep notifications minimal.

Useful notifications:

- Session starting soon
- Qualifying starting
- Race starting
- Favourite driver result
- Favourite driver podium
- Session finished

Do **not** spam users.

---

# 25. ANIMATION

Animations should communicate information.

Examples:

### Position changes

```text
P4 → P3
```

Use subtle movement.

### Session starts

```text
Countdown → LIVE
```

### Driver enters pit

```text
P3
↓
PIT
```

Use:

- Spring animations
- Short transitions
- Subtle opacity
- Number transitions

Avoid:

- Particle effects
- Excessive bouncing
- Neon effects
- Huge transitions

The product should feel fast, not flashy.

---

# 26. MICROINTERACTIONS

Add premium microinteractions:

- Haptic feedback where supported
- Smooth widget refresh
- Driver selection transitions
- Session status transitions
- Pull-to-refresh
- Subtle live indicators
- Smooth number changes

Every interaction should feel intentional.

---

# 27. RESPONSIVE DESIGN

Widgets must adapt to different sizes.

**Never simply scale the same layout.**

Create specific layouts for:

### Small

One key metric.

### Medium

Primary metric + supporting data.

### Large

Multiple information groups.

Example:

#### SMALL

```text
🔴 LIVE

P1
VER
```

#### MEDIUM

```text
🔴 LIVE
SINGAPORE GP

P1 VER
L42/62
```

#### LARGE

```text
🔴 LIVE
SINGAPORE GP

L42 / 62

1 VER
2 NOR +1.821
3 LEC +4.209
4 PIA +6.821
```

---

# 28. ACCESSIBILITY

Support:

- Dynamic font scaling
- High contrast
- Screen readers
- Reduced motion
- Color-blind-friendly status indicators

Never communicate information using color alone.

For example:

```text
P1 ●
```

not just:

```text
green = P1
```

---

# 29. PERFORMANCE

The widget experience must be extremely lightweight.

Priorities:

1. Fast launch
2. Low memory
3. Low battery usage
4. Efficient network usage
5. Cached data
6. Minimal background activity

Widgets should load almost instantly.

---

# 30. SECURITY

Never expose:

- API keys
- Database credentials
- Private tokens

Use environment variables.

Implement:

- HTTPS
- API authentication where necessary
- Rate limiting
- Input validation

---

# 31. UI QUALITY BAR

Before considering the UI complete, compare it mentally against:

- Apple's WidgetKit design quality
- Porsche digital interfaces
- F1 timing screens
- Linear
- Raycast
- Nothing OS
- Garmin
- Premium automotive dashboards

The result must **not** look like a student project.

It should look commercially shippable.

---

# 32. DESIGN DETAILS

Use:

- 8px spacing system
- Subtle 1px borders
- Very soft shadows
- Small corner radii
- Clear hierarchy
- Tabular numbers
- Uppercase metadata
- Minimal icons
- Strong alignment

Use whitespace intelligently.

Do not fill every available pixel.

---

# 33. EMPTY STATES

Design beautiful empty states.

Example:

```text
NO LIVE SESSION

Next session:

QUALIFYING
SAT · 21:00

Starts in
04:22:18
```

---

# 34. ERROR STATES

Example:

```text
LIVE DATA UNAVAILABLE

Using cached data

Updated 42 seconds ago

Retry
```

Do not show technical stack traces.

---

# 35. LOADING STATES

Use skeleton loading.

Avoid generic circular loading indicators wherever possible.

---

# 36. PROJECT STRUCTURE

Organize the repository professionally.

Suggested:

```text
/backend
    /api
    /models
    /services
    /data
    /cache
    /schemas
    /tests

/ios
    /APEX
    /Widgets
    /LiveActivities

/android
    /app
    /widgets

/windows
    /APEX
    /Widgets

/shared
    /design-tokens
    /api-schema

/docs
```

---

# 37. DEVELOPMENT APPROACH

Do **not** attempt to build everything simultaneously.

Build in this order:

### PHASE 1
Design system + branding

### PHASE 2
Backend + F1 data ingestion

### PHASE 3
API

### PHASE 4
iOS widgets

### PHASE 5
Android widgets

### PHASE 6
Windows widgets

### PHASE 7
Real-time timing

### PHASE 8
Notifications

### PHASE 9
Customization

### PHASE 10
Performance + polish

---

# 38. IMPORTANT IMPLEMENTATION RULE

Whenever you have a choice between:

> "more features"

and

> "better execution"

choose:

**BETTER EXECUTION.**

Five extremely polished widgets are better than twenty mediocre widgets.

---

# 39. FIRST DELIVERABLE

Start by creating:

1. Complete product architecture
2. Design system
3. Brand identity
4. Widget UI specifications
5. Backend architecture
6. Database schema
7. API specification
8. Project folder structure
9. Development roadmap

Then implement the MVP.

Do not skip directly into random UI code.

---

# 40. FINAL DESIGN TEST

Before declaring the project complete, ask:

### Can someone understand the current F1 situation in 2 seconds?

### Does every widget look good at its smallest supported size?

### Does it look like a premium motorsport product?

### Does the UI work equally well on iOS, Android and Windows?

### Does the product still look good without color?

### Does the widget feel useful without opening the app?

### Does live information update intelligently?

### Does anything look like a generic template?

If any answer is **NO**, redesign it.

---

# FINAL PRODUCT GOAL

The finished product should feel like:

> **A digital F1 pit wall sitting on your phone and desktop.**

Minimal.

Fast.

Live.

Beautiful.

Technical.

And completely focused on glanceable motorsport information.
