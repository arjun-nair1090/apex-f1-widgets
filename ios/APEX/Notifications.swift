import UserNotifications

/// Minimal by design (spec §24). Session starts are scheduled locally from the schedule, so no push server is needed.
/// Results are announced when a background refresh sees a new result for the favourite driver.
enum Notifications {
    enum Kind: String, CaseIterable, Identifiable {
        case sessionSoon = "Session starting soon"
        case qualifying = "Qualifying starting"
        case race = "Race starting"
        case driverResult = "Favourite driver result"
        case driverPodium = "Favourite driver podium"
        case sessionFinished = "Session finished"
        var id: String { rawValue }
        var defaultOn: Bool { self != .sessionSoon && self != .sessionFinished }
    }

    static func isOn(_ k: Kind) -> Bool { Prefs.defaults.object(forKey: "notify.\(k)") as? Bool ?? k.defaultOn }
    static func set(_ k: Kind, _ on: Bool) { Prefs.defaults.set(on, forKey: "notify.\(k)") }

    static func requestPermission() async -> Bool {
        (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])) ?? false
    }

    static func schedule(for snap: WidgetSnapshot) async {
        let center = UNUserNotificationCenter.current()
        guard await center.notificationSettings().authorizationStatus == .authorized, let race = snap.race else { return }
        center.removePendingNotificationRequests(withIdentifiers: race.sessions.flatMap { ["start.\($0.id)", "end.\($0.id)"] })
        for s in race.sessions where s.startsAt > .now {
            let kind: Kind = s.type == "RACE" ? .race : s.type == "QUALIFYING" ? .qualifying : .sessionSoon
            if isOn(kind) {
                let lead: TimeInterval = kind == .sessionSoon ? 15 * 60 : 5 * 60
                add(center, id: "start.\(s.id)", at: s.startsAt.addingTimeInterval(-lead),
                    title: "\(Fmt.title(s.label)) in \(Int(lead / 60)) min", body: race.name)
            }
            if isOn(.sessionFinished) {
                add(center, id: "end.\(s.id)", at: s.endsAt, title: "\(Fmt.title(s.label)) finished", body: "Results are in the APEX widget.")
            }
        }
    }

    static func announceResult(_ snap: WidgetSnapshot) {
        guard let d = snap.driver, let race = snap.race,
              let r = d.weekend.last(where: { $0.position != nil && $0.sessionType != "SPRINT_QUALIFYING" }),
              let pos = r.position else { return }
        let key = "announced.\(race.season).\(race.round).\(r.sessionType).\(d.id)"
        guard !Prefs.defaults.bool(forKey: key) else { return }
        Prefs.defaults.set(true, forKey: key)
        let podium = r.sessionType == "RACE" && pos <= 3
        guard podium ? isOn(.driverPodium) || isOn(.driverResult) : isOn(.driverResult) else { return }
        let what = r.sessionType == "QUALIFYING" ? "qualified" : "finished"
        add(UNUserNotificationCenter.current(), id: key, at: nil,
            title: podium ? "\(d.lastName) on the podium" : "\(d.lastName) \(what) P\(pos)",
            body: "\(race.name) · P\(pos)\(r.gap.map { " · \($0)" } ?? "")")
    }

    private static func add(_ center: UNUserNotificationCenter, id: String, at date: Date?, title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.threadIdentifier = "apex"
        let trigger = date.map {
            UNCalendarNotificationTrigger(dateMatching: Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: $0), repeats: false)
        }
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger))
    }
}
