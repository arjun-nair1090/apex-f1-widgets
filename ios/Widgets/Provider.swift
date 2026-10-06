import SwiftUI
import WidgetKit

struct APEXEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot?
    let staleSince: Date?
    let density: Density
    var showStats = true
    var showLast5 = true
    let theme = Prefs.theme
    let accent = Prefs.accent
    let teamColors = Prefs.teamColors

    /// Race Mode re-evaluated at this entry's date, so Countdown → LIVE happens without a fetch (spec §8, §15).
    var mode: Mode {
        guard let snapshot, let sessions = snapshot.race?.sessions else { return .next }
        let (m, _) = RaceMode.mode(sessions, at: date)
        if m == .results, snapshot.results == nil { // nothing classified yet: fall through like the backend
            let up = sessions.first { $0.startsAt > date }
            return up.map { $0.startsAt.timeIntervalSince(date) <= RaceMode.countdownWindow ? .countdown : .next } ?? .next
        }
        return m
    }

    var nextSession: Session? {
        snapshot?.race?.sessions.sorted { $0.startsAt < $1.startsAt }.first { $0.endsAt > date } ?? snapshot?.nextSession
    }

    static let placeholder = APEXEntry(date: .now, snapshot: nil, staleSince: nil, density: .standard)
}

enum Timelines {
    static func build(driver: String?, season: Int? = nil, density: Density,
                      configure: (inout APEXEntry) -> Void = { _ in }) async -> Timeline<APEXEntry> {
        let now = Date()
        let result = await APIClient.snapshot(driver: driver ?? Prefs.driver, season: season)
        let snap = result?.snapshot
        var dates: [Date] = [now]
        if let sessions = snap?.race?.sessions {
            dates += RaceMode.boundaries(sessions, after: now).prefix(16)
            // Day rollovers so "02 DAYS" becomes "01 DAYS" on time.
            for s in sessions where s.startsAt > now {
                for d in 1...7 {
                    let t = s.startsAt.addingTimeInterval(-Double(d) * 86400)
                    if t > now { dates.append(t) }
                }
            }
        }
        let entries = Array(Set(dates)).sorted().prefix(40).map { date -> APEXEntry in
            var e = APEXEntry(date: date, snapshot: snap, staleSince: result?.staleSince, density: density)
            configure(&e)
            return e
        }
        let live = entries.first?.mode == .live
        let nextBoundary = dates.filter { $0 > now }.min() ?? now.addingTimeInterval(1800)
        // Live: as often as WidgetKit's budget allows. Offline: retry in 5 min. Otherwise: at the next session boundary.
        let reload: Date = live ? now.addingTimeInterval(60)
            : result?.staleSince != nil ? now.addingTimeInterval(300)
            : min(nextBoundary, now.addingTimeInterval(1800))
        return Timeline(entries: Array(entries), policy: .after(reload))
    }
}

struct APEXProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> APEXEntry { .placeholder }

    func snapshot(for configuration: APEXConfigIntent, in context: Context) async -> APEXEntry {
        let cached = APIClient.cached()
        return APEXEntry(date: .now, snapshot: cached?.snapshot, staleSince: nil, density: configuration.density.density)
    }

    func timeline(for configuration: APEXConfigIntent, in context: Context) async -> Timeline<APEXEntry> {
        await Timelines.build(driver: configuration.driver?.id, density: configuration.density.density)
    }
}

struct DriverProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> APEXEntry { .placeholder }

    func snapshot(for configuration: DriverConfigIntent, in context: Context) async -> APEXEntry {
        APEXEntry(date: .now, snapshot: APIClient.cached()?.snapshot, staleSince: nil, density: .standard)
    }

    func timeline(for configuration: DriverConfigIntent, in context: Context) async -> Timeline<APEXEntry> {
        await Timelines.build(driver: configuration.driver?.id, season: configuration.season, density: .standard) {
            $0.showStats = configuration.showStats
            $0.showLast5 = configuration.showLast5
        }
    }
}
