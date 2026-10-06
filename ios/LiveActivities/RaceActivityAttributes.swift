import ActivityKit
import Foundation

/// Shared by the app (starts/updates the activity from the SSE stream) and the widget extension (renders it).
struct RaceActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        struct Car: Codable, Hashable {
            let position: Int
            let code: String
            let gap: String?
            let inPit: Bool
        }

        var phase: String          // "RACE", "Q3", …
        var lap: Int?
        var lapsTotal: Int?
        var top: [Car]             // first three
        var favourite: Car?
        var final: Bool

        init(timing t: Timing, favourite code: String?) {
            phase = t.phase ?? Fmt.sessionShort(t.sessionType)
            lap = t.lap
            lapsTotal = t.lapsTotal
            let car = { (r: TimingRow) in Car(position: r.position, code: r.code, gap: r.position == 1 && !t.isRace ? r.time : r.gap, inPit: r.inPit) }
            top = t.rows.prefix(3).map(car)
            favourite = t.rows.first { $0.code == code }.map(car)
            final = t.final
        }
    }

    let raceName: String       // "SINGAPORE GP"
    let countryCode: String?
    let sessionEnds: Date
}
