import BackgroundTasks
import SwiftUI
import UserNotifications
import WidgetKit

@main
struct APEXApp: App {
    @StateObject private var model = AppModel()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .preferredColorScheme(model.theme == .light ? .light : .dark)
                .task { await model.refresh() }
                .onChange(of: phase) { _, p in if p == .active { Task { await model.refresh() } } }
        }
        .backgroundTask(.appRefresh("club.apex.refresh")) {
            // Re-schedule first so the chain continues even if this run is cut short.
            let req = BGAppRefreshTaskRequest(identifier: "club.apex.refresh")
            req.earliestBeginDate = .now.addingTimeInterval(30 * 60)
            try? BGTaskScheduler.shared.submit(req)
            if let snap = await APIClient.snapshot(driver: Prefs.driver)?.snapshot {
                await Notifications.schedule(for: snap)
                Notifications.announceResult(snap)
                WidgetCenter.shared.reloadAllTimelines()
            }
        }
    }
}

/// Widget customization (spec §19): preview on top, controls below, preview updates immediately.
struct RootView: View {
    @EnvironmentObject private var model: AppModel
    @State private var widget = WidgetKind.raceMode
    @State private var family = WidgetFamily.systemMedium
    @State private var notificationsAllowed = false

    enum WidgetKind: String, CaseIterable, Identifiable {
        case raceMode = "APEX", next = "Next session", countdown = "Countdown", timing = "Live timing", driver = "Driver",
             favourite = "Favourite driver", wdc = "Drivers' title", wcc = "Constructors' title", weekend = "Race weekend"
        var id: String { rawValue }
    }

    private var palette: Palette { Palette.of(model.theme) }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    preview
                        .frame(maxWidth: .infinity)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                    Picker("Size", selection: $family) {
                        Text("Small").tag(WidgetFamily.systemSmall)
                        Text("Medium").tag(WidgetFamily.systemMedium)
                        Text("Large").tag(WidgetFamily.systemLarge)
                    }
                    .pickerStyle(.segmented)
                    .listRowBackground(Color.clear)
                } header: { Text("Your widget") }

                Section("Widget") {
                    Picker("Widget", selection: $widget) {
                        ForEach(WidgetKind.allCases) { Text($0.rawValue).tag($0) }
                    }
                    Picker("Driver", selection: $model.driver) {
                        Text("None").tag(String?.none)
                        ForEach(model.drivers, id: \.id) { d in Text("\(d.firstName) \(d.lastName)").tag(Optional(d.id)) }
                    }
                    Picker("Information", selection: $model.density) {
                        ForEach(Density.allCases, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Style") {
                    Picker("Theme", selection: $model.theme) {
                        Text("Dark").tag(Theme.dark); Text("AMOLED").tag(Theme.amoled); Text("Light").tag(Theme.light)
                    }
                    .pickerStyle(.segmented)
                    Picker("Accent", selection: $model.accent) {
                        Text("System").tag(Accent.system); Text("Team color").tag(Accent.team); Text("Motorsport red").tag(Accent.red)
                    }
                    Toggle("Show team colors", isOn: $model.teamColors)
                }

                if model.snapshot?.live != nil {
                    Section("Live") {
                        Button(model.liveActivityOn ? "Stop Live Activity" : "Follow on Lock Screen") { model.toggleLiveActivity() }
                    }
                }

                Section {
                    if notificationsAllowed {
                        ForEach(Notifications.Kind.allCases) { k in
                            Toggle(k.rawValue, isOn: Binding(get: { Notifications.isOn(k) },
                                                             set: { Notifications.set(k, $0); Task { await model.refresh() } }))
                        }
                    } else {
                        Button("Turn on notifications") { Task { notificationsAllowed = await Notifications.requestPermission() } }
                    }
                } header: { Text("Notifications") } footer: { Text("A few a weekend at most.") }

                Section("Data") { dataStatus }
            }
            .scrollContentBackground(.hidden)
            .background(palette.background)
            .refreshable { await model.refresh() }
            .navigationTitle("APEX")
            .sensoryFeedback(.selection, trigger: widget)
            .sensoryFeedback(.selection, trigger: model.driver)
            .sensoryFeedback(.selection, trigger: family)
            .task {
                notificationsAllowed = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus == .authorized
            }
        }
    }

    /// Renders the real widget views (Widgets/Views.swift) at real sizes.
    private var preview: some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            let e = APEXEntry(date: ctx.date, snapshot: model.snapshot, staleSince: model.staleSince, density: model.density)
            let look = Look(e)
            Group {
                if model.snapshot == nil {
                    Skeleton(rows: family == .systemSmall ? 2 : family == .systemMedium ? 3 : 9)
                } else {
                    switch widget {
                    case .raceMode: RaceModeView(e: e)
                    case .next: NextSessionView(e: e)
                    case .countdown: CountdownView(e: e)
                    case .timing: TimingView(e: e, results: e.mode == .results)
                    case .driver: DriverView(e: e)
                    case .favourite: FavouriteView(e: e)
                    case .wdc: StandingsView(e: e, kind: .drivers)
                    case .wcc: StandingsView(e: e, kind: .constructors)
                    case .weekend: WeekendView(e: e)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .padding(16)
            .frame(width: family == .systemSmall ? 170 : 364, height: family == .systemLarge ? 382 : 170)
            .background(look.p.surface, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(look.p.border, lineWidth: 1))
            .environment(\.look, look)
            .environment(\.apexFamily, family)
            .animation(.spring(response: 0.35, dampingFraction: 0.86), value: widget)
            .animation(.spring(response: 0.35, dampingFraction: 0.86), value: family)
        }
    }

    @ViewBuilder private var dataStatus: some View {
        if let s = model.status {
            ForEach(s.sources.keys.sorted(), id: \.self) { k in
                LabeledContent(k == "jolpica" ? "Schedule & standings" : "Live timing") {
                    let src = s.sources[k]!
                    Text(src.ok ? "● OK" : "○ Unavailable").foregroundStyle(src.ok ? Tokens.sectorPersonal : palette.t2)
                }
            }
            if let since = model.staleSince {
                LabeledContent("Showing cached data") { Text("\(Fmt.ago(since, now: .now).lowercased()) ago") }
            }
        } else {
            Text("Checking…").foregroundStyle(palette.t2)
        }
    }
}
