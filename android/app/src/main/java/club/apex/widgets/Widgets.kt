package club.apex.widgets

import android.content.Context
import android.os.SystemClock
import android.util.TypedValue
import android.widget.RemoteViews
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.LocalContext
import androidx.glance.LocalSize
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.AndroidRemoteViews
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.LinearProgressIndicator
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.appWidgetBackground
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.ColumnScope
import androidx.glance.layout.Row
import androidx.glance.layout.RowScope
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.semantics.contentDescription
import androidx.glance.semantics.semantics
import androidx.glance.text.FontFamily
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextAlign
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import club.apex.Accent
import club.apex.Density
import club.apex.DriverDetail
import club.apex.Fmt
import club.apex.MainActivity
import club.apex.Mode
import club.apex.Palette
import club.apex.Prefs
import club.apex.R
import club.apex.RaceMode
import club.apex.Repository
import club.apex.Session
import club.apex.Theme
import club.apex.Timing
import club.apex.TimingRow
import club.apex.Tokens
import club.apex.WidgetSnapshot
import club.apex.hex
import java.time.Duration
import java.time.Instant

// Spec §27: three real layouts, picked from the launcher-reported size. Never a scaled layout.
private val SMALL = DpSize(120.dp, 120.dp)
private val MEDIUM = DpSize(250.dp, 120.dp)
private val LARGE = DpSize(250.dp, 280.dp)

enum class Size { S, M, L }
enum class Kind { RACE, NEXT, COUNTDOWN, TIMING, DRIVER, FAVOURITE, WDC, WCC, WEEKEND }

/** Everything a widget needs to draw one frame. */
class Frame(val snap: WidgetSnapshot?, val staleSince: Instant?, val now: Instant, val density: Density,
            val p: Palette, val accent: Color, val teamColors: Boolean) {
    val mode get() = snap?.let { RaceMode.modeOf(it, now) } ?: Mode.NEXT
    val next get() = snap?.let { RaceMode.nextSession(it, now) }
    val favourite get() = snap?.driver?.code
}

open class ApexWidget(private val kind: Kind) : GlanceAppWidget() {
    override val sizeMode = SizeMode.Responsive(setOf(SMALL, MEDIUM, LARGE))

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val prefs = Prefs(context)
        val loaded = Repository.cached(context)
        val theme = prefs.theme
        val accent = when (prefs.accent) {
            Accent.SYSTEM -> if (theme == Theme.LIGHT) Tokens.signalOnLight else Tokens.signal
            Accent.TEAM -> loaded?.snapshot?.driver?.teamColor?.let(::hex) ?: Tokens.signal
            Accent.RED -> Tokens.motorsportRed
        }
        // Worker writes the cache on success; "stale" means it is older than the refresh cadence.
        val stale = loaded?.staleSince?.takeIf { Duration.between(it, Instant.now()) > Duration.ofMinutes(2) }
        val frame = Frame(loaded?.snapshot, stale, Instant.now(), prefs.density, Palette.of(theme), accent, prefs.teamColors)
        provideContent { Shell(frame) { Body(kind, frame) } }
    }

    companion object {
        val all = Kind.entries.map { widgetFor(it) }
        fun widgetFor(k: Kind): ApexWidget = when (k) {
            Kind.RACE -> RaceModeWidget(); Kind.NEXT -> NextSessionWidget(); Kind.COUNTDOWN -> CountdownWidget()
            Kind.TIMING -> LiveTimingWidget(); Kind.DRIVER -> DriverWidget(); Kind.FAVOURITE -> FavouriteDriverWidget()
            Kind.WDC -> WdcWidget(); Kind.WCC -> WccWidget(); Kind.WEEKEND -> WeekendWidget()
        }
        suspend fun updateEverything(context: Context) = all.forEach { it.updateAll(context) }
    }
}

class RaceModeWidget : ApexWidget(Kind.RACE)
class NextSessionWidget : ApexWidget(Kind.NEXT)
class CountdownWidget : ApexWidget(Kind.COUNTDOWN)
class LiveTimingWidget : ApexWidget(Kind.TIMING)
class DriverWidget : ApexWidget(Kind.DRIVER)
class FavouriteDriverWidget : ApexWidget(Kind.FAVOURITE)
class WdcWidget : ApexWidget(Kind.WDC)
class WccWidget : ApexWidget(Kind.WCC)
class WeekendWidget : ApexWidget(Kind.WEEKEND)

open class ApexReceiver(kind: Kind) : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = ApexWidget.widgetFor(kind)
    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        RefreshWorker.runNow(context)
    }
}

class RaceModeReceiver : ApexReceiver(Kind.RACE)
class NextSessionReceiver : ApexReceiver(Kind.NEXT)
class CountdownReceiver : ApexReceiver(Kind.COUNTDOWN)
class LiveTimingReceiver : ApexReceiver(Kind.TIMING)
class DriverReceiver : ApexReceiver(Kind.DRIVER)
class FavouriteDriverReceiver : ApexReceiver(Kind.FAVOURITE)
class WdcReceiver : ApexReceiver(Kind.WDC)
class WccReceiver : ApexReceiver(Kind.WCC)
class WeekendReceiver : ApexReceiver(Kind.WEEKEND)

// ---------- primitives ----------

@Composable private fun size(): Size {
    val s = LocalSize.current
    return when { s.width < 200.dp -> Size.S; s.height >= 250.dp -> Size.L; else -> Size.M }
}

private fun c(color: Color) = ColorProvider(color)

@Composable private fun T(text: String, color: Color, size: TextUnit = 13.sp, mono: Boolean = false,
                          weight: FontWeight = FontWeight.Medium, modifier: GlanceModifier = GlanceModifier,
                          align: TextAlign = TextAlign.Start) =
    Text(text, modifier, TextStyle(color = c(color), fontSize = size, fontWeight = weight,
        fontFamily = if (mono) FontFamily.Monospace else null, textAlign = align), maxLines = 1)

/** Small uppercase metadata. */
@Composable private fun Meta(text: String, color: Color, modifier: GlanceModifier = GlanceModifier) =
    T(text.uppercase(), color, 11.sp, weight = FontWeight.Bold, modifier = modifier)

@Composable private fun Micro(text: String, color: Color) = T(text.uppercase(), color, 9.sp, weight = FontWeight.Bold)

@Composable private fun Shell(f: Frame, content: @Composable ColumnScope.() -> Unit) {
    Column(GlanceModifier.fillMaxSize().appWidgetBackground().background(f.p.surface)
        .cornerRadius(android.R.dimen.system_app_widget_background_radius)
        .padding(16.dp).clickable(actionStartActivity<MainActivity>())) {
        if (f.snap == null) Skeleton(f) else content()
    }
}

@Composable private fun ColumnScope.Skeleton(f: Frame) {
    Box(GlanceModifier.width(64.dp).height(10.dp).background(f.p.elevated).cornerRadius(3.dp)) {}
    Spacer(GlanceModifier.defaultWeight())
    repeat(if (size() == Size.L) 9 else 3) {
        Box(GlanceModifier.fillMaxWidth().height(10.dp).background(f.p.elevated).cornerRadius(3.dp)) {}
        Spacer(GlanceModifier.height(8.dp))
    }
}

@Composable private fun RowScope.Fill() = Spacer(GlanceModifier.defaultWeight())
@Composable private fun ColumnScope.Fill() = Spacer(GlanceModifier.defaultWeight())
@Composable private fun Gap(h: Int) = Spacer(GlanceModifier.height(h.dp))

@Composable private fun LiveTag(f: Frame, label: String?) = Row(verticalAlignment = Alignment.CenterVertically,
    modifier = GlanceModifier.semantics { contentDescription = "Live ${label ?: ""}" }) {
    // Glance can't animate; the pulse lives in the app (DESIGN_SYSTEM.md §6).
    Box(GlanceModifier.size(6.dp).background(f.accent).cornerRadius(3.dp)) {}
    Spacer(GlanceModifier.width(6.dp))
    Meta(if (label != null) "LIVE · $label" else "LIVE", f.accent)
}

/** The apex rail: 2px progress (DESIGN_SYSTEM.md §5). */
@Composable private fun Rail(f: Frame, fraction: Float, on: Boolean) {
    Gap(6)
    LinearProgressIndicator(fraction.coerceIn(0f, 1f), GlanceModifier.fillMaxWidth().height(2.dp),
        color = c(if (on) f.accent else f.p.t1), backgroundColor = c(f.p.border))
}

@Composable private fun Tick(f: Frame, color: String?) {
    val col = if (f.teamColors && color != null) hex(color) else Color.Transparent
    Box(GlanceModifier.width(2.dp).height(11.dp).background(col)) {}
}

@Composable private fun RaceHeader(f: Frame, trailing: String? = null) = Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
    val race = f.snap?.race
    T(Fmt.flag(race?.countryCode), f.p.t1, 13.sp)
    Spacer(GlanceModifier.width(6.dp))
    Meta(race?.shortName ?: "", f.p.t1)
    Fill()
    if (trailing != null) Meta(trailing, f.p.t3)
}

@Composable private fun Stale(f: Frame) {
    val since = f.staleSince ?: return
    Gap(4)
    Micro("Last updated ${Fmt.ago(since, f.now)} ago", f.p.t3)
}

/** HH:MM:SS that ticks on the home screen with no refresh: a platform Chronometer in count-down mode. */
@Composable private fun Countdown(f: Frame, target: Instant, sp: Float) {
    val total = Duration.between(f.now, target)
    val days = total.toDays()
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (days > 0) {
            T("${days}D", f.p.t1, sp.sp, mono = true, weight = FontWeight.Bold)
            Spacer(GlanceModifier.width(8.dp))
        }
        val context = LocalContext.current
        val rv = RemoteViews(context.packageName, R.layout.countdown).apply {
            val untilDayBoundary = total.minusDays(days).toMillis()
            setChronometer(R.id.chrono, SystemClock.elapsedRealtime() + untilDayBoundary, null, true)
            setChronometerCountDown(R.id.chrono, true)
            setTextColor(R.id.chrono, f.p.t1.toArgb())
            setTextViewTextSize(R.id.chrono, TypedValue.COMPLEX_UNIT_SP, sp)
        }
        AndroidRemoteViews(rv)
    }
}

// ---------- widgets ----------

@Composable private fun ColumnScope.Body(kind: Kind, f: Frame) = when (kind) {
    Kind.RACE -> when (f.mode) {
        Mode.LIVE -> TimingBody(f, results = false)
        Mode.RESULTS -> TimingBody(f, results = true)
        Mode.COUNTDOWN -> CountdownBody(f, f.next)
        Mode.NEXT -> NextBody(f)
    }
    Kind.NEXT -> NextBody(f)
    Kind.COUNTDOWN -> CountdownBody(f, f.snap?.race?.sessions?.firstOrNull { it.type == "RACE" })
    Kind.TIMING -> TimingBody(f, results = f.mode == Mode.RESULTS)
    Kind.DRIVER -> DriverBody(f)
    Kind.FAVOURITE -> FavouriteBody(f)
    Kind.WDC -> StandingsBody(f, drivers = true)
    Kind.WCC -> StandingsBody(f, drivers = false)
    Kind.WEEKEND -> WeekendBody(f)
}

@Composable private fun ColumnScope.NextBody(f: Frame) {
    val s = f.next ?: run { Meta("Season complete", f.p.t2); return }
    if (RaceMode.state(s, f.now) == "live") return TimingBody(f, results = false)
    val soon = RaceMode.state(s, f.now) == "starting_soon"
    when (size()) {
        Size.S -> {
            Row(verticalAlignment = Alignment.CenterVertically) {
                T(Fmt.flag(f.snap?.race?.countryCode), f.p.t1); Spacer(GlanceModifier.width(6.dp))
                Meta(f.snap?.race?.shortName?.removeSuffix(" GP") ?: "", f.p.t1)
            }
            Fill()
            Meta(s.label, f.p.t1)
            Meta(Fmt.dayTime(s.start), f.p.t3)
            Gap(8)
            Countdown(f, s.start, 20f)
        }
        else -> {
            RaceHeader(f, if (soon) "◐ SOON" else "R${f.snap?.race?.round ?: ""}")
            if (size() == Size.L) { Gap(16); WeekendRows(f) }
            Fill()
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                Column {
                    T(Fmt.title(s.label), f.p.t1, 17.sp, weight = FontWeight.Bold)
                    Meta(Fmt.dayTime(s.start), f.p.t3)
                }
                Fill()
                Column(horizontalAlignment = Alignment.End) {
                    Meta("Starts in", f.p.t3)
                    Countdown(f, s.start, if (size() == Size.L) 36f else 28f)
                }
            }
        }
    }
    Stale(f)
}

@Composable private fun ColumnScope.CountdownBody(f: Frame, target: Session?) {
    val s = target ?: return NextBody(f)
    val st = RaceMode.state(s, f.now)
    if (st == "live" || st == "finished") return Body(Kind.RACE, f)  // LIVE at lights out, no tap needed (spec §8)
    val name = Fmt.sessionShort(s.type)
    val days = Duration.between(f.now, s.start).toDays()
    when (size()) {
        Size.S -> {
            Meta("$name in", f.p.t2)
            Fill()
            if (days > 0) { T(Fmt.pad(days.toInt()), f.p.t1, 32.sp, mono = true, weight = FontWeight.Bold); Micro("Days", f.p.t3); Gap(8) }
            Countdown(f, s.start.minus(Duration.ofDays(days)), if (days > 0) 20f else 30f)
        }
        else -> {
            Row(GlanceModifier.fillMaxWidth()) { Meta("$name starts in", f.p.t2); Fill(); Meta(f.snap?.race?.shortName ?: "", f.p.t1) }
            Row(GlanceModifier.fillMaxWidth()) { Fill(); Meta(Fmt.dayTime(s.start), f.p.t3) }
            Fill()
            Row(verticalAlignment = Alignment.Bottom) {
                if (days > 0) {
                    Column { T(Fmt.pad(days.toInt()), f.p.t1, 40.sp, mono = true, weight = FontWeight.Bold); Micro("Days", f.p.t3) }
                    Spacer(GlanceModifier.width(20.dp))
                }
                Countdown(f, s.start.minus(Duration.ofDays(days)), if (size() == Size.L) 52f else 40f)
            }
            if (size() == Size.L) { Fill(); Meta(f.snap?.race?.circuitName ?: "", f.p.t3) }
        }
    }
    Stale(f)
}

@Composable private fun ColumnScope.TimingBody(f: Frame, results: Boolean) {
    val t = (if (results) f.snap?.results else f.snap?.live) ?: return EmptyLive(f)
    val label = t.phase ?: Fmt.sessionShort(t.sessionType)
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        if (t.final) Meta("✓ Final · $label", f.p.t1) else LiveTag(f, if (size() == Size.S) null else label)
        Fill()
        t.lap?.let { lap -> T(if (size() == Size.S || t.lapsTotal == null) "L$lap" else "L$lap / ${t.lapsTotal}", f.p.t1, 11.sp, mono = true, weight = FontWeight.Bold) }
    }
    when (size()) {
        Size.S -> {
            Fill()
            t.rows.firstOrNull()?.let { p1 ->
                T("P${p1.position}", f.p.t1, 32.sp, mono = true, weight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically) { Tick(f, p1.teamColor); Spacer(GlanceModifier.width(6.dp)); T(p1.code, f.p.t1, 17.sp, weight = FontWeight.Bold) }
            }
        }
        Size.M -> {
            Fill()
            val rows = visibleRows(t, if (f.density == Density.MINIMAL) 3 else 6, f.favourite)
            Row(GlanceModifier.fillMaxWidth()) {
                Column(GlanceModifier.defaultWeight()) { rows.take(3).forEach { TimingLine(f, t, it) } }
                if (rows.size > 3) {
                    Spacer(GlanceModifier.width(16.dp))
                    Column(GlanceModifier.defaultWeight()) { rows.drop(3).forEach { TimingLine(f, t, it) } }
                }
            }
        }
        Size.L -> {
            Gap(6); RaceHeader(f)
            Fill()
            val n = when (f.density) { Density.MINIMAL -> 6; Density.STANDARD -> 10; Density.DETAILED -> 12 }
            visibleRows(t, n, f.favourite).forEach { TimingLine(f, t, it, sectors = f.density != Density.MINIMAL, interval = f.density == Density.DETAILED) }
        }
    }
    if (!t.final) {
        val session = f.snap?.race?.sessions?.firstOrNull { it.id == t.sessionId }
        val frac = if (t.lap != null && t.lapsTotal != null) t.lap.toFloat() / t.lapsTotal
            else session?.let { Duration.between(it.start, f.now).toMillis().toFloat() / Duration.between(it.start, it.end).toMillis() } ?: 0f
        Rail(f, frac, on = true)
    }
    Stale(f)
}

private fun visibleRows(t: Timing, n: Int, fav: String?): List<TimingRow> {
    val rows = t.rows.take(n)
    val f = t.rows.firstOrNull { it.code == fav }
    return if (f != null && n > 2 && f !in rows) rows.dropLast(1) + f else rows
}

@Composable private fun TimingLine(f: Frame, t: Timing, r: TimingRow, sectors: Boolean = false, interval: Boolean = false) {
    val fav = r.code == f.favourite
    Row(GlanceModifier.fillMaxWidth().height(18.dp), verticalAlignment = Alignment.CenterVertically) {
        // Favourite: a 2px Signal bar (never a filled row).
        Box(GlanceModifier.width(2.dp).height(14.dp).background(if (fav) f.accent else Color.Transparent)) {}
        T("${r.position}", f.p.t2, mono = true, modifier = GlanceModifier.width(22.dp), align = TextAlign.End)
        Spacer(GlanceModifier.width(6.dp)); Tick(f, r.teamColor); Spacer(GlanceModifier.width(6.dp))
        T(r.code, f.p.t1, mono = true, weight = if (fav) FontWeight.Bold else FontWeight.Medium)
        Fill()
        if (sectors) {
            // Glyph + color: readable without color (spec §28).
            r.sectors?.forEach { s ->
                when (s) {
                    "purple" -> T("◆", Tokens.sectorOverall, 9.sp); "green" -> T("▲", Tokens.sectorPersonal, 9.sp)
                    "yellow" -> T("–", Tokens.sectorNone, 9.sp); else -> T("·", f.p.t3, 9.sp)
                }
            }
            Spacer(GlanceModifier.width(8.dp))
        }
        when {
            r.inPit -> T("PIT", f.p.t1, 10.sp, weight = FontWeight.Bold)
            r.position == 1 -> T(if (!t.isRace || t.final) r.time ?: "" else "", f.p.t1, mono = true)
            else -> T(r.gap ?: "", f.p.t2, mono = true)
        }
        if (interval && r.interval != null) { Spacer(GlanceModifier.width(6.dp)); T(r.interval, f.p.t3, mono = true) }
    }
}

@Composable private fun ColumnScope.EmptyLive(f: Frame) {
    val s = f.next
    if (f.mode == Mode.LIVE) {
        LiveTag(f, s?.let { Fmt.sessionShort(it.type) })
        Fill()
        if (f.snap?.liveUnavailable == true) {
            // Spec §34
            Meta("Live data unavailable", f.p.t1)
            if (size() != Size.S) T("Using cached data", f.p.t2)
            Gap(8)
            T("RETRY", f.p.t1, 11.sp, weight = FontWeight.Bold, modifier = GlanceModifier.clickable(actionRunCallback<RefreshAction>()))
        } else {
            Meta(f.snap?.race?.shortName ?: "", f.p.t1)
            T("Timing is on its way", f.p.t2)
        }
    } else if (s != null) {
        // Spec §33
        Meta("No live session", f.p.t2)
        Fill()
        if (size() != Size.S) Micro("Next session", f.p.t3)
        Meta(s.label, f.p.t1)
        Meta(Fmt.dayTime(s.start), f.p.t3)
        Gap(6)
        Countdown(f, s.start, if (size() == Size.S) 20f else 28f)
    } else Meta("No live session", f.p.t2)
    Stale(f)
}

@Composable private fun ColumnScope.DriverBody(f: Frame) {
    val d = f.snap?.driver ?: return ChooseDriver(f)
    val pos = d.position?.let { "P$it" } ?: "—"
    when (size()) {
        Size.S -> {
            Meta(d.teamName ?: "", f.p.t2)
            Fill()
            T(pos, f.p.t1, 32.sp, mono = true, weight = FontWeight.Bold)
            Row(verticalAlignment = Alignment.CenterVertically) { Tick(f, d.teamColor); Spacer(GlanceModifier.width(6.dp)); T(d.code, f.p.t1, 17.sp, weight = FontWeight.Bold) }
            T("${Fmt.points(d.points)} PTS", f.p.t3, mono = true)
        }
        else -> {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Tick(f, d.teamColor); Spacer(GlanceModifier.width(8.dp))
                T("${d.firstName} ${d.lastName}".uppercase(), f.p.t1, 15.sp, weight = FontWeight.Bold)
                Fill(); T(Fmt.flag(d.countryCode), f.p.t1); Spacer(GlanceModifier.width(4.dp)); Meta(d.teamName ?: "", f.p.t2)
            }
            Fill()
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                T(pos, f.p.t1, if (size() == Size.L) 64.sp else 40.sp, mono = true, weight = FontWeight.Bold)
                Fill(); T(Fmt.points(d.points), f.p.t1, 22.sp, mono = true, weight = FontWeight.Bold); Spacer(GlanceModifier.width(4.dp)); Meta("PTS", f.p.t3)
            }
            if (f.density != Density.MINIMAL) {
                Gap(12)
                Row { Stat(f, "Wins", d.wins); Stat(f, "Podiums", d.podiums); Stat(f, "Poles", d.poles) }
            }
            if (size() == Size.L && d.last5.isNotEmpty()) {
                Gap(16); Micro("Last ${d.last5.size}", f.p.t3); Gap(6)
                Row { d.last5.forEachIndexed { i, p -> T(p?.let { "P$it" } ?: "DNF", if (i == 0) f.p.t1 else f.p.t2, mono = true); Spacer(GlanceModifier.width(10.dp)) } }
            }
        }
    }
    Stale(f)
}

@Composable private fun Stat(f: Frame, label: String, v: Int) = Column(GlanceModifier.padding(end = 16.dp)) {
    Micro(label, f.p.t3); T("$v", f.p.t1, 15.sp, mono = true, weight = FontWeight.Bold)
}

@Composable private fun ColumnScope.ChooseDriver(f: Frame) {
    Meta("Driver", f.p.t2); Fill()
    T("Choose a driver", f.p.t1, 17.sp, weight = FontWeight.Bold)
    T("Tap to open APEX", f.p.t2)
}

@Composable private fun ColumnScope.FavouriteBody(f: Frame) {
    val d: DriverDetail = f.snap?.driver ?: return ChooseDriver(f)
    val liveRow = if (f.mode == Mode.LIVE) f.snap.live?.rows?.firstOrNull { it.code == d.code } else null
    val race = d.weekend.firstOrNull { it.sessionType == "RACE" && it.position != null }
    val quali = d.weekend.firstOrNull { it.sessionType == "QUALIFYING" && it.position != null }
    // The widget picks what matters now (spec §14).
    val (big, top, sub) = when {
        liveRow != null -> Triple("P${liveRow.position}", f.snap.live?.lap?.let { "L$it" } ?: "",
            if (liveRow.inPit) "PIT" else if (liveRow.position == 1) (if (f.snap.live?.isRace == true) "LEADER" else liveRow.time ?: "") else liveRow.gap ?: "")
        race != null -> Triple("P${race.position}", "", race.gap ?: if (race.position == 1) "WINNER" else "")
        quali != null -> Triple("QUALI P${quali.position}", "", "")
        else -> Triple(d.position?.let { "P$it" } ?: "—", "", "${Fmt.points(d.points)} PTS")
    }
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        when {
            liveRow != null -> LiveTag(f, f.snap.live?.let { it.phase ?: Fmt.sessionShort(it.sessionType) })
            race != null -> Meta("✓ Race", f.p.t1)
            quali != null -> Meta("Grid", f.p.t2)
            else -> Meta("Championship", f.p.t2)
        }
        Fill()
        if (size() != Size.S) Meta("${d.firstName} ${d.lastName}", f.p.t1)
    }
    Fill()
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
        T(big, f.p.t1, if (big.length > 4) 22.sp else if (size() == Size.S) 32.sp else 44.sp, mono = true, weight = FontWeight.Bold)
        Fill(); T(top, f.p.t1, 11.sp, mono = true, weight = FontWeight.Bold)
    }
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Tick(f, d.teamColor); Spacer(GlanceModifier.width(6.dp)); T(d.code, f.p.t1, 17.sp, weight = FontWeight.Bold)
        Fill(); T(sub, f.p.t2, mono = true)
    }
    Stale(f)
}

@Composable private fun ColumnScope.StandingsBody(f: Frame, drivers: Boolean) {
    data class Line(val pos: Int, val name: String, val color: String?, val points: Double, val fav: Boolean)
    val snap = f.snap ?: return
    val all = if (drivers) snap.drivers.map { Line(it.position, it.code, it.teamColor, it.points, it.code == f.favourite) }
        else snap.constructors.map { Line(it.position, it.shortName, it.color, it.points, it.teamId == snap.driver?.teamId) }
    val n = when (size()) { Size.S -> 3; Size.M -> if (f.density == Density.MINIMAL) 3 else 5; Size.L -> if (f.density == Density.MINIMAL) 6 else 10 }
    var shown = all.take(n)
    if (shown.none { it.fav }) {
        val fav = all.firstOrNull { it.fav } ?: snap.driver?.takeIf { drivers && it.position != null }
            ?.let { Line(it.position!!, it.code, it.teamColor, it.points, true) }
        if (fav != null && n > 2) shown = shown.dropLast(1) + fav
    }
    Row(GlanceModifier.fillMaxWidth()) {
        Meta(if (drivers) "WDC" else "WCC", f.p.t1); Fill()
        if (size() != Size.S) snap.race?.let { Meta("After R${maxOf(1, it.round - 1)}", f.p.t3) }
    }
    Fill()
    val leader = all.firstOrNull()?.points ?: 0.0
    shown.forEach { l ->
        Row(GlanceModifier.fillMaxWidth().height(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(GlanceModifier.width(2.dp).height(14.dp).background(if (l.fav) f.accent else Color.Transparent)) {}
            T(Fmt.pad(l.pos), f.p.t2, mono = true, modifier = GlanceModifier.width(24.dp), align = TextAlign.End)
            Spacer(GlanceModifier.width(6.dp)); Tick(f, l.color); Spacer(GlanceModifier.width(6.dp))
            T(l.name, f.p.t1, if (drivers) 13.sp else 12.sp, mono = drivers, weight = if (drivers) FontWeight.Medium else FontWeight.Bold)
            Fill()
            if (size() == Size.L && f.density == Density.DETAILED && l.pos > 1) {
                T("−${Fmt.points(leader - l.points)}", f.p.t3, mono = true); Spacer(GlanceModifier.width(12.dp))
            }
            T(Fmt.points(l.points), f.p.t1, mono = true)
        }
    }
    Stale(f)
}

@Composable private fun WeekendRows(f: Frame) {
    f.snap?.race?.sessions?.forEach { s ->
        val st = RaceMode.state(s, f.now)
        val color = when (st) { "finished" -> f.p.t3; "live" -> f.accent; else -> f.p.t1 }
        val glyph = when (st) { "finished" -> "✓"; "live" -> "●"; "starting_soon" -> "◐"; else -> "○" }
        Row(GlanceModifier.fillMaxWidth().height(20.dp), verticalAlignment = Alignment.CenterVertically) {
            T(Fmt.day(s.start), f.p.t3, 10.sp, weight = FontWeight.Bold, modifier = GlanceModifier.width(34.dp))
            T(s.label, color, 13.sp, weight = FontWeight.Bold)
            Fill()
            T(glyph, color, 13.sp, mono = true, modifier = GlanceModifier.semantics { contentDescription = st.replace('_', ' ') })
            Spacer(GlanceModifier.width(8.dp))
            T(when (st) { "live" -> "LIVE"; "finished" -> ""; else -> Fmt.hhmm(s.start) }, if (st == "live") f.accent else f.p.t2, 12.sp, mono = true,
                modifier = GlanceModifier.width(40.dp), align = TextAlign.End)
        }
    }
}

@Composable private fun ColumnScope.WeekendBody(f: Frame) {
    val race = f.snap?.race ?: run { Meta("No upcoming weekend", f.p.t2); return }
    if (size() == Size.S) {
        Meta(race.shortName.removeSuffix(" GP"), f.p.t1)
        Gap(12)
        Row {
            race.sessions.forEach { s ->
                val st = RaceMode.state(s, f.now)
                T(when (st) { "finished" -> "✓"; "live" -> "●"; else -> "○" }, when (st) { "live" -> f.accent; "finished" -> f.p.t3; else -> f.p.t1 }, 15.sp, mono = true)
                Spacer(GlanceModifier.width(6.dp))
            }
        }
        Fill()
        f.next?.let { s ->
            val live = RaceMode.state(s, f.now) == "live"
            Meta(if (live) "● ${s.label}" else s.label, if (live) f.accent else f.p.t1)
            Meta(if (live) "Live now" else Fmt.dayTime(s.start), f.p.t3)
        }
    } else {
        RaceHeader(f, "R${race.round}")
        if (size() == Size.M) Fill() else Gap(16)
        WeekendRows(f)
        if (size() == Size.L) {
            Gap(12); Micro(race.circuitName, f.p.t3)
            Fill()
            f.next?.takeIf { RaceMode.state(it, f.now) != "live" }?.let { s ->
                Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                    Column { Micro("Next", f.p.t3); T(s.label, f.p.t1, 17.sp, weight = FontWeight.Bold) }
                    Fill(); Countdown(f, s.start, 28f)
                }
            }
        }
    }
    Stale(f)
}
