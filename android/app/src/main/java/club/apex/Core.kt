package club.apex

import android.content.Context
import androidx.core.content.edit
import androidx.compose.ui.graphics.Color
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

// ---------- Tokens (mirror of shared/design-tokens/tokens.json) ----------

enum class Theme { DARK, AMOLED, LIGHT }
enum class Accent { SYSTEM, TEAM, RED }
enum class Density { MINIMAL, STANDARD, DETAILED }

data class Palette(val background: Color, val surface: Color, val elevated: Color, val border: Color,
                   val t1: Color, val t2: Color, val t3: Color) {
    companion object {
        fun of(theme: Theme) = when (theme) {
            Theme.DARK -> Palette(hex("08090B"), hex("111318"), hex("181B21"), hex("23262E"), hex("F5F7FA"), hex("9298A3"), hex("5C626D"))
            Theme.AMOLED -> Palette(Color.Black, Color.Black, hex("0C0D10"), hex("1C1F25"), hex("F5F7FA"), hex("9298A3"), hex("5C626D"))
            Theme.LIGHT -> Palette(hex("F3F4F6"), Color.White, hex("F0F1F4"), hex("E2E4E9"), hex("0B0D11"), hex("5A606B"), hex("8C919B"))
        }
    }
}

object Tokens {
    val signal = hex("FF5A1F")
    val signalOnLight = hex("E0440C")
    val motorsportRed = hex("E10D2E")
    val sectorOverall = hex("A879FF")
    val sectorPersonal = hex("2FD27F")
    val sectorNone = hex("E8C547")
}

fun hex(h: String): Color = Color(0xFF000000 or h.removePrefix("#").toLong(16))

// ---------- Models (mirror of backend/apex/schemas.py) ----------

@Serializable data class Session(val id: String, val round: Int, val type: String, val label: String,
                                 val startsAt: String, val endsAt: String, val state: String) {
    val start: Instant get() = parseInstant(startsAt)
    val end: Instant get() = parseInstant(endsAt)
}
@Serializable data class Race(val season: Int, val round: Int, val name: String, val shortName: String,
                              val circuitName: String, val countryCode: String? = null, val lapsTotal: Int? = null,
                              val sessions: List<Session>)
@Serializable data class DriverStanding(val position: Int, val driverId: String, val code: String, val name: String,
                                        val teamId: String? = null, val teamColor: String? = null, val points: Double, val wins: Int)
@Serializable data class ConstructorStanding(val position: Int, val teamId: String, val name: String, val shortName: String,
                                             val color: String? = null, val points: Double, val wins: Int)
@Serializable data class WeekendResult(val sessionType: String, val position: Int? = null, val gap: String? = null)
@Serializable data class DriverDetail(val id: String, val code: String, val firstName: String, val lastName: String,
                                      val countryCode: String? = null, val teamId: String? = null, val teamName: String? = null,
                                      val teamColor: String? = null, val position: Int? = null, val points: Double,
                                      val wins: Int, val podiums: Int, val poles: Int, val last5: List<Int?>,
                                      val weekend: List<WeekendResult>)
@Serializable data class DriverSummary(val id: String, val code: String, val firstName: String, val lastName: String,
                                       val teamName: String? = null)
@Serializable data class TimingRow(val position: Int, val driverNumber: Int, val code: String, val teamColor: String? = null,
                                   val time: String? = null, val gap: String? = null, val interval: String? = null,
                                   val sectors: List<String?>? = null, val inPit: Boolean, val drs: Boolean? = null)
@Serializable data class Timing(val sessionId: String, val sessionType: String, val phase: String? = null, val lap: Int? = null,
                                val lapsTotal: Int? = null, val final: Boolean, val updatedAt: String, val rows: List<TimingRow>) {
    val isRace get() = sessionType == "RACE" || sessionType == "SPRINT"
}
@Serializable data class WidgetSnapshot(val generatedAt: String, val mode: String, val race: Race? = null,
                                        val nextSession: Session? = null, val live: Timing? = null, val results: Timing? = null,
                                        val drivers: List<DriverStanding>, val constructors: List<ConstructorStanding>,
                                        val driver: DriverDetail? = null, val liveUnavailable: Boolean)

@Serializable data class SourceStatus(val ok: Boolean, val lastSuccess: String? = null)
@Serializable data class Status(val ok: Boolean, val live: Boolean, val liveUnavailable: Boolean, val sources: Map<String, SourceStatus>)

fun parseInstant(s: String): Instant = OffsetDateTime.parse(s).toInstant()

@OptIn(ExperimentalSerializationApi::class)
val json = Json { ignoreUnknownKeys = true; namingStrategy = JsonNamingStrategy.SnakeCase }

// ---------- Preferences (set in the companion app, read by every widget) ----------

class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("apex", Context.MODE_PRIVATE)
    var driver: String? get() = sp.getString("driver", null); set(v) = sp.edit { putString("driver", v) }
    var theme: Theme get() = enumOr(sp.getString("theme", null), Theme.DARK); set(v) = sp.edit { putString("theme", v.name) }
    var accent: Accent get() = enumOr(sp.getString("accent", null), Accent.SYSTEM); set(v) = sp.edit { putString("accent", v.name) }
    var density: Density get() = enumOr(sp.getString("density", null), Density.STANDARD); set(v) = sp.edit { putString("density", v.name) }
    var teamColors: Boolean get() = sp.getBoolean("teamColors", true); set(v) = sp.edit { putBoolean("teamColors", v) }
    fun notify(kind: String, default: Boolean) = sp.getBoolean("notify.$kind", default)
    fun setNotify(kind: String, on: Boolean) = sp.edit { putBoolean("notify.$kind", on) }
    fun once(key: String): Boolean = !sp.getBoolean(key, false).also { if (!it) sp.edit { putBoolean(key, true) } }

    private inline fun <reified T : Enum<T>> enumOr(name: String?, default: T) =
        enumValues<T>().firstOrNull { it.name == name } ?: default
}

// ---------- Repository: one request per refresh, last good snapshot on disk (spec §23) ----------

data class Loaded(val snapshot: WidgetSnapshot, val staleSince: Instant?)

object Repository {
    private fun cacheFile(context: Context) = File(context.filesDir, "snapshot.json")

    fun cached(context: Context): Loaded? = runCatching {
        val s = json.decodeFromString<WidgetSnapshot>(cacheFile(context).readText())
        Loaded(s, parseInstant(s.generatedAt))
    }.getOrNull()

    /** Blocking; call from a worker or IO dispatcher. */
    fun fetch(context: Context): Loaded? = runCatching {
        val driver = Prefs(context).driver
        val text = get("api/widgets/snapshot" + (driver?.let { "?driver=" + URLEncoder.encode(it, "UTF-8") } ?: ""))
        val snap = json.decodeFromString<WidgetSnapshot>(text)
        cacheFile(context).writeText(text)
        Loaded(snap, null)
    }.getOrElse { cached(context) }

    fun drivers(): List<DriverSummary> = runCatching { json.decodeFromString<List<DriverSummary>>(get("api/drivers")) }.getOrDefault(emptyList())

    fun status(): Status? = runCatching { json.decodeFromString<Status>(get("api/status")) }.getOrNull()

    private fun get(path: String): String {
        val conn = URL("${BuildConfig.BASE_URL}/$path").openConnection() as HttpURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 10_000
        try {
            check(conn.responseCode == 200) { "HTTP ${conn.responseCode}" }
            return conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }
}

// ---------- Race Mode (mirror of backend/apex/racemode.py) ----------

enum class Mode { LIVE, RESULTS, COUNTDOWN, NEXT }

object RaceMode {
    private val SOON = Duration.ofMinutes(15)
    private val RESULTS_WINDOW = Duration.ofMinutes(90)
    val COUNTDOWN_WINDOW: Duration = Duration.ofHours(3)

    fun state(s: Session, now: Instant) = when {
        now >= s.end -> "finished"
        now >= s.start -> "live"
        now >= s.start - SOON -> "starting_soon"
        else -> "upcoming"
    }

    fun mode(sessions: List<Session>, now: Instant): Pair<Mode, Session?> {
        val ordered = sessions.sortedBy { it.start }
        ordered.firstOrNull { it.start <= now && now < it.end }?.let { return Mode.LIVE to it }
        ordered.lastOrNull { it.end <= now }?.let { if (Duration.between(it.end, now) < RESULTS_WINDOW) return Mode.RESULTS to it }
        val up = ordered.firstOrNull { it.start > now } ?: return Mode.NEXT to null
        return (if (Duration.between(now, up.start) <= COUNTDOWN_WINDOW) Mode.COUNTDOWN else Mode.NEXT) to up
    }

    /** Snapshot mode at [now], falling back like the backend when there is nothing classified to show. */
    fun modeOf(s: WidgetSnapshot, now: Instant): Mode {
        val sessions = s.race?.sessions ?: return Mode.NEXT
        val (m, _) = mode(sessions, now)
        if (m != Mode.RESULTS || s.results != null) return m
        val up = sessions.firstOrNull { it.start > now } ?: return Mode.NEXT
        return if (Duration.between(now, up.start) <= COUNTDOWN_WINDOW) Mode.COUNTDOWN else Mode.NEXT
    }

    fun boundaries(sessions: List<Session>, now: Instant): List<Instant> = sessions.flatMap {
        listOf(it.start - COUNTDOWN_WINDOW, it.start - SOON, it.start, it.end, it.end + RESULTS_WINDOW)
    }.filter { it > now }.sorted()

    fun nextSession(s: WidgetSnapshot, now: Instant) = s.race?.sessions?.sortedBy { it.start }?.firstOrNull { it.end > now } ?: s.nextSession
}

object Fmt {
    private val zone get() = ZoneId.systemDefault()
    private val hm = DateTimeFormatter.ofPattern("HH:mm")
    fun day(i: Instant) = i.atZone(zone).dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.ENGLISH).uppercase()
    fun hhmm(i: Instant): String = hm.format(i.atZone(zone))
    fun dayTime(i: Instant) = "${day(i)} · ${hhmm(i)}"
    fun points(p: Double) = if (p % 1.0 == 0.0) p.toInt().toString() else "%.1f".format(p)
    fun pad(n: Int) = n.toString().padStart(2, '0')
    fun flag(cc: String?) = if (cc?.length != 2) "" else cc.uppercase().map { String(Character.toChars(0x1F1A5 + it.code)) }.joinToString("")
    fun ago(since: Instant, now: Instant): String { val s = Duration.between(since, now).seconds
        return if (s < 60) "${s}S" else if (s < 3600) "${s / 60}M" else "${s / 3600}H" }
    /** "QUALIFYING" → "Qualifying", but "FP1" stays "FP1". */
    fun title(label: String) = if (label.any(Char::isDigit)) label else label.lowercase().replaceFirstChar { it.uppercase() }
    fun sessionShort(t: String) = mapOf("QUALIFYING" to "QUALI", "SPRINT_QUALIFYING" to "SPRINT QUALI")[t] ?: t
    /** "2D 03:11" past a day, "HH:MM:SS" inside one. */
    fun countdown(target: Instant, now: Instant): String {
        val s = Duration.between(now, target).seconds.coerceAtLeast(0)
        val d = s / 86400; val h = s % 86400 / 3600; val m = s % 3600 / 60; val sec = s % 60
        return if (d > 0) "${d}D ${pad(h.toInt())}:${pad(m.toInt())}" else "${pad(h.toInt())}:${pad(m.toInt())}:${pad(sec.toInt())}"
    }
}
