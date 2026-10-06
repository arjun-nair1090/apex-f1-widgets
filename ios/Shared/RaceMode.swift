import Foundation

// Mirror of backend/apex/racemode.py. Evaluated per timeline entry so widgets flip at boundaries offline.

enum Mode: String { case live, results, countdown, next }

enum RaceMode {
    static let soon: TimeInterval = 15 * 60
    static let resultsWindow: TimeInterval = 90 * 60
    static let countdownWindow: TimeInterval = 3 * 3600

    static func state(_ s: Session, at now: Date) -> String {
        if now >= s.endsAt { return "finished" }
        if now >= s.startsAt { return "live" }
        if now >= s.startsAt.addingTimeInterval(-soon) { return "starting_soon" }
        return "upcoming"
    }

    static func mode(_ sessions: [Session], at now: Date) -> (Mode, Session?) {
        let ordered = sessions.sorted { $0.startsAt < $1.startsAt }
        if let live = ordered.first(where: { $0.startsAt <= now && now < $0.endsAt }) { return (.live, live) }
        if let ended = ordered.last(where: { $0.endsAt <= now }), now.timeIntervalSince(ended.endsAt) < resultsWindow {
            return (.results, ended)
        }
        guard let up = ordered.first(where: { $0.startsAt > now }) else { return (.next, nil) }
        return (up.startsAt.timeIntervalSince(now) <= countdownWindow ? .countdown : .next, up)
    }

    /// Instants where the widget must re-render without a network call.
    static func boundaries(_ sessions: [Session], after now: Date) -> [Date] {
        sessions.flatMap { [$0.startsAt.addingTimeInterval(-countdownWindow), $0.startsAt.addingTimeInterval(-soon),
                             $0.startsAt, $0.endsAt, $0.endsAt.addingTimeInterval(resultsWindow)] }
            .filter { $0 > now }.sorted()
    }
}

enum Fmt {
    static func dayTime(_ d: Date) -> String {
        d.formatted(.dateTime.weekday(.abbreviated)).uppercased() + " · " + d.formatted(.dateTime.hour(.twoDigits(amPM: .omitted)).minute(.twoDigits))
    }
    static func day(_ d: Date) -> String { d.formatted(.dateTime.weekday(.abbreviated)).uppercased() }
    static func hhmm(_ d: Date) -> String { d.formatted(.dateTime.hour(.twoDigits(amPM: .omitted)).minute(.twoDigits)) }
    static func points(_ p: Double) -> String { p.rounded() == p ? String(Int(p)) : String(format: "%.1f", p) }
    static func pad(_ n: Int) -> String { n < 10 ? "0\(n)" : "\(n)" }
    static func flag(_ cc: String?) -> String {
        guard let cc, cc.count == 2 else { return "" }
        return String(String.UnicodeScalarView(cc.uppercased().unicodeScalars.compactMap { Unicode.Scalar(127397 + $0.value) }))
    }
    static func ago(_ since: Date, now: Date) -> String {
        let s = Int(now.timeIntervalSince(since))
        return s < 60 ? "\(s)S" : s < 3600 ? "\(s / 60)M" : "\(s / 3600)H"
    }
    /// "QUALIFYING" → "Qualifying", but "FP1" stays "FP1".
    static func title(_ label: String) -> String { label.contains(where: \.isNumber) ? label : label.capitalized }
    static func sessionShort(_ type: String) -> String {
        ["RACE": "RACE", "SPRINT": "SPRINT", "QUALIFYING": "QUALI", "SPRINT_QUALIFYING": "SPRINT QUALI"][type] ?? type
    }
    /// Whole days left, and the date at which the HH:MM:SS timer should hit zero for the current day.
    static func countdownParts(to target: Date, now: Date) -> (days: Int, dayBoundary: Date) {
        let days = max(0, Int(target.timeIntervalSince(now) / 86400))
        return (days, target.addingTimeInterval(-Double(days) * 86400))
    }
}
