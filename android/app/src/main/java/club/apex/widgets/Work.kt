package club.apex.widgets

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.glance.GlanceId
import androidx.glance.action.ActionParameters
import androidx.glance.appwidget.action.ActionCallback
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import club.apex.Fmt
import club.apex.MainActivity
import club.apex.Mode
import club.apex.Prefs
import club.apex.R
import club.apex.RaceMode
import club.apex.Repository
import club.apex.WidgetSnapshot
import java.time.Duration
import java.time.Instant
import java.util.concurrent.TimeUnit

/**
 * Fetch → cache → redraw every widget → schedule the next run.
 * Cadence: 1 min while live, at the next session boundary otherwise (max 30 min), 5 min when offline.
 */
class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val loaded = Repository.fetch(applicationContext)
        ApexWidget.updateEverything(applicationContext)
        val now = Instant.now()
        val snap = loaded?.snapshot
        if (snap != null) {
            Alerts.scheduleSessionStarts(applicationContext, snap, now)
            Alerts.announceResult(applicationContext, snap)
            Alerts.liveProgress(applicationContext, snap, now)
        }
        val live = snap?.let { RaceMode.modeOf(it, now) } == Mode.LIVE
        val next = snap?.race?.sessions?.let { RaceMode.boundaries(it, now).firstOrNull() }
        val delay = when {
            live -> Duration.ofMinutes(1)
            loaded?.staleSince != null -> Duration.ofMinutes(5)
            next != null -> Duration.between(now, next).coerceIn(Duration.ofSeconds(30), Duration.ofMinutes(30))
            else -> Duration.ofMinutes(30)
        }
        schedule(applicationContext, delay)
        return Result.success()
    }

    companion object {
        private const val NAME = "apex-refresh"
        fun runNow(context: Context) = schedule(context, Duration.ZERO)
        private fun schedule(context: Context, delay: Duration) {
            val req = OneTimeWorkRequestBuilder<RefreshWorker>().setInitialDelay(delay.toMillis(), TimeUnit.MILLISECONDS).build()
            WorkManager.getInstance(context).enqueueUniqueWork(NAME, ExistingWorkPolicy.REPLACE, req)
        }
    }
}

/** "Retry" on the live-data-unavailable state (spec §34). */
class RefreshAction : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) = RefreshWorker.runNow(context)
}

/** Minimal notifications (spec §24). Session starts are scheduled locally from the schedule. */
object Alerts {
    enum class Kind(val label: String, val default: Boolean) {
        SESSION_SOON("Session starting soon", false), QUALIFYING("Qualifying starting", true), RACE("Race starting", true),
        DRIVER_RESULT("Favourite driver result", true), DRIVER_PODIUM("Favourite driver podium", true),
        SESSION_FINISHED("Session finished", false), LIVE_PROGRESS("Live progress in notifications", false),
    }

    private const val CHANNEL = "apex"
    private const val LIVE_ID = 1

    fun enabled(context: Context, k: Kind) = Prefs(context).notify(k.name, k.default)

    private fun ensureChannel(context: Context) {
        context.getSystemService(NotificationManager::class.java)
            .createNotificationChannel(NotificationChannel(CHANNEL, "Sessions and results", NotificationManager.IMPORTANCE_DEFAULT))
    }

    fun scheduleSessionStarts(context: Context, snap: WidgetSnapshot, now: Instant) {
        val race = snap.race ?: return
        val wm = WorkManager.getInstance(context)
        for (s in race.sessions) {
            val kind = when (s.type) { "RACE" -> Kind.RACE; "QUALIFYING" -> Kind.QUALIFYING; else -> Kind.SESSION_SOON }
            val lead = if (kind == Kind.SESSION_SOON) Duration.ofMinutes(15) else Duration.ofMinutes(5)
            val at = s.start - lead
            if (at.isAfter(now) && enabled(context, kind)) {
                enqueue(wm, "start.${s.id}", Duration.between(now, at),
                    "${Fmt.title(s.label)} in ${lead.toMinutes()} min", race.shortName)
            } else wm.cancelUniqueWork("start.${s.id}")
            if (s.end.isAfter(now) && enabled(context, Kind.SESSION_FINISHED)) {
                enqueue(wm, "end.${s.id}", Duration.between(now, s.end), "${Fmt.title(s.label)} finished", "Results are on your APEX widget.")
            }
        }
    }

    private fun enqueue(wm: WorkManager, name: String, delay: Duration, title: String, body: String) {
        val req = OneTimeWorkRequestBuilder<NotifyWorker>().setInitialDelay(delay.toMillis(), TimeUnit.MILLISECONDS)
            .setInputData(Data.Builder().putString("title", title).putString("body", body).build()).build()
        wm.enqueueUniqueWork(name, ExistingWorkPolicy.REPLACE, req)
    }

    fun announceResult(context: Context, snap: WidgetSnapshot) {
        val d = snap.driver ?: return
        val race = snap.race ?: return
        val r = d.weekend.lastOrNull { it.position != null && it.sessionType != "SPRINT_QUALIFYING" } ?: return
        val pos = r.position ?: return
        if (!Prefs(context).once("announced.${race.season}.${race.round}.${r.sessionType}.${d.id}")) return
        val podium = r.sessionType == "RACE" && pos <= 3
        if (!(if (podium) enabled(context, Kind.DRIVER_PODIUM) || enabled(context, Kind.DRIVER_RESULT) else enabled(context, Kind.DRIVER_RESULT))) return
        val verb = if (r.sessionType == "QUALIFYING") "qualified" else "finished"
        post(context, (race.round * 10 + r.sessionType.length), if (podium) "${d.lastName} on the podium" else "${d.lastName} $verb P$pos",
            "${race.shortName} · P$pos${r.gap?.let { " · $it" } ?: ""}")
    }

    /** Ongoing notification with lap progress while live (opt-in). */
    fun liveProgress(context: Context, snap: WidgetSnapshot, now: Instant) {
        val nm = NotificationManagerCompat.from(context)
        val t = snap.live
        if (t == null || RaceMode.modeOf(snap, now) != Mode.LIVE || !enabled(context, Kind.LIVE_PROGRESS)) {
            nm.cancel(LIVE_ID); return
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        ensureChannel(context)
        val fav = t.rows.firstOrNull { it.code == snap.driver?.code }
        val leader = t.rows.firstOrNull()
        val text = listOfNotNull(leader?.let { "${it.code} leads" }, fav?.let { "${it.code} P${it.position}${if (it.inPit) " · PIT" else it.gap?.let { g -> " $g" } ?: ""}" }).joinToString(" · ")
        val n = NotificationCompat.Builder(context, CHANNEL).setSmallIcon(R.drawable.ic_apex)
            .setContentTitle("● LIVE · ${t.phase ?: Fmt.sessionShort(t.sessionType)}${t.lap?.let { " · L$it${t.lapsTotal?.let { total -> " / $total" } ?: ""}" } ?: ""}")
            .setContentText(text).setOngoing(true).setOnlyAlertOnce(true).setSilent(true)
            .setProgress(t.lapsTotal ?: 0, t.lap ?: 0, t.lapsTotal == null)
            .setContentIntent(openApp(context)).build()
        nm.notify(LIVE_ID, n)
    }

    fun post(context: Context, id: Int, title: String, body: String) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        ensureChannel(context)
        NotificationManagerCompat.from(context).notify(id, NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_apex).setContentTitle(title).setContentText(body)
            .setContentIntent(openApp(context)).setAutoCancel(true).build())
    }

    private fun openApp(context: Context) = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
}

class NotifyWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        Alerts.post(applicationContext, id.hashCode(), inputData.getString("title") ?: return Result.success(), inputData.getString("body") ?: "")
        return Result.success()
    }
}
