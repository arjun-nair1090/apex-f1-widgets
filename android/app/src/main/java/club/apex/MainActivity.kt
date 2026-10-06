package club.apex

import android.Manifest
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.FrameLayout
import android.widget.RemoteViews
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.compose
import club.apex.widgets.Alerts
import club.apex.widgets.ApexWidget
import club.apex.widgets.CountdownReceiver
import club.apex.widgets.DriverReceiver
import club.apex.widgets.FavouriteDriverReceiver
import club.apex.widgets.Kind
import club.apex.widgets.LiveTimingReceiver
import club.apex.widgets.NextSessionReceiver
import club.apex.widgets.RaceModeReceiver
import club.apex.widgets.RefreshWorker
import club.apex.widgets.WccReceiver
import club.apex.widgets.WdcReceiver
import club.apex.widgets.WeekendReceiver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Companion app (spec §17): configure + preview widgets. Not a news app. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ApexApp() }
    }
}

private val names = mapOf(
    Kind.RACE to "APEX", Kind.NEXT to "Next session", Kind.COUNTDOWN to "Countdown", Kind.TIMING to "Live timing",
    Kind.DRIVER to "Driver", Kind.FAVOURITE to "Favourite driver", Kind.WDC to "Drivers' title", Kind.WCC to "Constructors' title",
    Kind.WEEKEND to "Race weekend",
)
private val receivers: Map<Kind, Class<out GlanceAppWidgetReceiver>> = mapOf(
    Kind.RACE to RaceModeReceiver::class.java, Kind.NEXT to NextSessionReceiver::class.java, Kind.COUNTDOWN to CountdownReceiver::class.java,
    Kind.TIMING to LiveTimingReceiver::class.java, Kind.DRIVER to DriverReceiver::class.java, Kind.FAVOURITE to FavouriteDriverReceiver::class.java,
    Kind.WDC to WdcReceiver::class.java, Kind.WCC to WccReceiver::class.java, Kind.WEEKEND to WeekendReceiver::class.java,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ApexApp() {
    val context = LocalContext.current
    val prefs = remember { Prefs(context) }
    val haptics = LocalHapticFeedback.current
    val scope = rememberCoroutineScope()
    var theme by remember { mutableStateOf(prefs.theme) }
    var accent by remember { mutableStateOf(prefs.accent) }
    var density by remember { mutableStateOf(prefs.density) }
    var teamColors by remember { mutableStateOf(prefs.teamColors) }
    var driver by remember { mutableStateOf(prefs.driver) }
    var kind by remember { mutableStateOf(Kind.RACE) }
    var size by remember { mutableStateOf("M") }
    var drivers by remember { mutableStateOf(emptyList<DriverSummary>()) }
    var status by remember { mutableStateOf<Status?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    var version by remember { mutableIntStateOf(0) }  // bumps re-render the preview
    var canNotify by remember { mutableStateOf(Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) }

    suspend fun refresh() {
        refreshing = true
        withContext(Dispatchers.IO) {
            Repository.fetch(context)
            if (drivers.isEmpty()) drivers = Repository.drivers()
            status = Repository.status()
        }
        ApexWidget.updateEverything(context)
        RefreshWorker.runNow(context)
        version++
        refreshing = false
    }
    fun changed() { haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove); version++; scope.launch { ApexWidget.updateEverything(context) } }
    LaunchedEffect(Unit) { refresh() }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { canNotify = it }

    val p = Palette.of(theme)
    val scheme = if (theme == Theme.LIGHT) lightColorScheme(primary = Tokens.signalOnLight, background = p.background, surface = p.surface)
        else darkColorScheme(primary = Tokens.signal, background = p.background, surface = p.surface, onSurface = p.t1, onBackground = p.t1)
    MaterialTheme(colorScheme = scheme) {
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refresh() } },
            modifier = Modifier.fillMaxSize().background(p.background)) {
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                item { Spacer(Modifier.height(32.dp)); Text("APEX", fontSize = 28.sp, fontWeight = FontWeight.SemiBold, color = p.t1) }
                item {
                    Label("Your widget", p)
                    Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                        WidgetPreview(kind, size, version)
                    }
                    Segmented(listOf("S", "M", "L"), size, { mapOf("S" to "Small", "M" to "Medium", "L" to "Large")[it]!! }) { size = it; changed() }
                }
                item {
                    Label("Widget", p)
                    Dropdown(names[kind]!!, Kind.entries.map { names[it]!! }) { i -> kind = Kind.entries[i]; changed() }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = {
                        AppWidgetManager.getInstance(context).requestPinAppWidget(ComponentName(context, receivers.getValue(kind)), null, null)
                    }) { Text("Add to home screen") }
                }
                item {
                    Label("Driver", p)
                    val current = drivers.firstOrNull { it.id == driver }?.let { "${it.firstName} ${it.lastName}" } ?: "None"
                    Dropdown(current, listOf("None") + drivers.map { "${it.firstName} ${it.lastName}" }) { i ->
                        driver = if (i == 0) null else drivers[i - 1].id
                        prefs.driver = driver
                        scope.launch { refresh() }
                    }
                }
                item { Label("Information", p); Segmented(Density.entries, density, ::title) { density = it; prefs.density = it; changed() } }
                item { Label("Theme", p); Segmented(Theme.entries, theme, { if (it == Theme.AMOLED) "AMOLED" else title(it) }) { theme = it; prefs.theme = it; changed() } }
                item { Label("Accent", p); Segmented(Accent.entries, accent, { mapOf(Accent.SYSTEM to "System", Accent.TEAM to "Team", Accent.RED to "Red")[it]!! }) { accent = it; prefs.accent = it; changed() } }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Show team colors", color = p.t1, modifier = Modifier.weight(1f))
                        Switch(teamColors, { teamColors = it; prefs.teamColors = it; changed() })
                    }
                }
                item {
                    Label("Notifications", p)
                    if (!canNotify && Build.VERSION.SDK_INT >= 33) {
                        Button(onClick = { permission.launch(Manifest.permission.POST_NOTIFICATIONS) }) { Text("Turn on notifications") }
                    } else Alerts.Kind.entries.forEach { k ->
                        var on by remember { mutableStateOf(Alerts.enabled(context, k)) }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(k.label, color = p.t1, modifier = Modifier.weight(1f))
                            Switch(on, { on = it; prefs.setNotify(k.name, it); RefreshWorker.runNow(context) })
                        }
                    }
                }
                item {
                    Label("Data", p)
                    val s = status
                    if (s == null) Text("Can't reach the APEX service. Widgets keep showing the last data they received.", color = p.t2)
                    else s.sources.forEach { (name, src) ->
                        Row {
                            Text(if (name == "jolpica") "Schedule & standings" else "Live timing", color = p.t1, modifier = Modifier.weight(1f))
                            Text(if (src.ok) "● OK" else "○ Unavailable", color = if (src.ok) Tokens.sectorPersonal else p.t2)
                        }
                    }
                    Spacer(Modifier.height(48.dp))
                }
            }
        }
    }
}

private fun title(e: Enum<*>) = e.name.lowercase().replaceFirstChar { it.uppercase() }

@Composable private fun Label(text: String, p: Palette) = Text(text, color = p.t2, fontSize = 12.sp, modifier = Modifier.padding(bottom = 8.dp))

/** The real Glance widget rendered to RemoteViews: what you see is what the home screen gets. */
@Composable
private fun WidgetPreview(kind: Kind, size: String, version: Int) {
    val context = LocalContext.current
    val dp = when (size) { "S" -> DpSize(150.dp, 150.dp); "L" -> DpSize(320.dp, 320.dp); else -> DpSize(320.dp, 150.dp) }
    var views by remember { mutableStateOf<RemoteViews?>(null) }
    LaunchedEffect(kind, size, version) { views = ApexWidget.widgetFor(kind).compose(context, size = dp) }
    Box(Modifier.size(dp.width, dp.height)) {
        views?.let { rv ->
            AndroidView(factory = { FrameLayout(it) }, update = { frame ->
                frame.removeAllViews()
                frame.addView(rv.apply(frame.context, frame))
            }, modifier = Modifier.fillMaxSize())
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> Segmented(options: List<T>, selected: T, label: (T) -> String, onSelect: (T) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        options.forEachIndexed { i, o ->
            SegmentedButton(selected = o == selected, onClick = { onSelect(o) },
                shape = SegmentedButtonDefaults.itemShape(i, options.size)) { Text(label(o)) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Dropdown(current: String, options: List<String>, onPick: (Int) -> Unit) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        OutlinedTextField(current, {}, readOnly = true, singleLine = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(androidx.compose.material3.ExposedDropdownMenuAnchorType.PrimaryNotEditable))
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEachIndexed { i, o -> DropdownMenuItem(text = { Text(o) }, onClick = { open = false; onPick(i) }) }
        }
    }
}

