import ActivityKit
import SwiftUI
import WidgetKit

/// Companion-app state. The app only configures and previews widgets (spec §17), and bridges live timing to the Live Activity.
@MainActor
final class AppModel: ObservableObject {
    @Published var snapshot: WidgetSnapshot?
    @Published var staleSince: Date?
    @Published var drivers: [DriverSummary] = []
    @Published var status: ServiceStatus?
    @Published var liveActivityOn = false

    @Published var driver: String? = Prefs.driver { didSet { Prefs.driver = driver; changed(refetch: true) } }
    @Published var theme = Prefs.theme { didSet { Prefs.theme = theme; changed() } }
    @Published var accent = Prefs.accent { didSet { Prefs.accent = accent; changed() } }
    @Published var density = Prefs.density { didSet { Prefs.density = density; changed() } }
    @Published var teamColors = Prefs.teamColors { didSet { Prefs.teamColors = teamColors; changed() } }

    private var streamTask: Task<Void, Never>?

    struct ServiceStatus: Decodable {
        struct Source: Decodable { let ok: Bool; let lastSuccess: Date? }
        let ok: Bool
        let live: Bool
        let liveUnavailable: Bool
        let sources: [String: Source]
    }

    func refresh() async {
        let result = await APIClient.snapshot(driver: driver)
        snapshot = result?.snapshot
        staleSince = result?.staleSince
        if drivers.isEmpty { drivers = (try? await APIClient.drivers()) ?? [] }
        if let (data, _) = try? await URLSession.shared.data(from: APIClient.baseURL.appending(path: "api/status")) {
            status = try? JSONDecoder.apex.decode(ServiceStatus.self, from: data)
        }
        if let snapshot {
            await Notifications.schedule(for: snapshot)
            Notifications.announceResult(snapshot)
        }
        if snapshot?.mode == "live" { startStream() }
    }

    private func changed(refetch: Bool = false) {
        WidgetCenter.shared.reloadAllTimelines()
        if refetch { Task { await refresh() } }
        else { objectWillChange.send() }
    }

    // MARK: Live: SSE → in-app preview + Live Activity

    func startStream() {
        guard streamTask == nil else { return }
        streamTask = Task { [weak self] in
            let url = APIClient.baseURL.appending(path: "api/session/live/stream")
            while !Task.isCancelled {
                do {
                    let (bytes, _) = try await URLSession.shared.bytes(from: url)
                    for try await line in bytes.lines where line.hasPrefix("data: ") {
                        guard let timing = try? JSONDecoder.apex.decode(Timing.self, from: Data(line.dropFirst(6).utf8)) else { continue }
                        await self?.apply(timing)
                    }
                } catch {
                    try? await Task.sleep(for: .seconds(5))  // reconnect
                }
            }
        }
    }

    private func apply(_ timing: Timing) async {
        guard let s = snapshot else { return }
        snapshot = WidgetSnapshot(generatedAt: .now, mode: timing.final ? "results" : "live", race: s.race,
                                  nextSession: s.nextSession, live: timing.final ? nil : timing,
                                  results: timing.final ? timing : nil, drivers: s.drivers,
                                  constructors: s.constructors, driver: s.driver, liveUnavailable: false)
        let state = RaceActivityAttributes.ContentState(timing: timing, favourite: s.driver?.code)
        for activity in Activity<RaceActivityAttributes>.activities {
            await activity.update(ActivityContent(state: state, staleDate: .now.addingTimeInterval(120)))
            if timing.final { await activity.end(nil, dismissalPolicy: .after(.now.addingTimeInterval(900))) }
        }
        if timing.final { streamTask?.cancel(); streamTask = nil; liveActivityOn = false }
    }

    func toggleLiveActivity() {
        if liveActivityOn {
            Task { for a in Activity<RaceActivityAttributes>.activities { await a.end(nil, dismissalPolicy: .immediate) } }
            liveActivityOn = false
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled, let s = snapshot, let t = s.live,
              let session = s.race?.sessions.first(where: { $0.id == t.sessionId }) else { return }
        let attributes = RaceActivityAttributes(raceName: s.race?.shortName ?? "", countryCode: s.race?.countryCode,
                                                sessionEnds: session.endsAt)
        let state = RaceActivityAttributes.ContentState(timing: t, favourite: s.driver?.code)
        // ponytail: updates come from the app's SSE stream; add APNs push-to-update so it keeps ticking when iOS suspends the app.
        if (try? Activity.request(attributes: attributes, content: ActivityContent(state: state, staleDate: nil))) != nil {
            liveActivityOn = true
            startStream()
        }
    }
}
