import Foundation

/// One request per widget refresh. The last good snapshot is persisted in the App Group so a widget is never empty (spec §23).
enum APIClient {
    static let appGroup = "group.club.apex"
    static var baseURL: URL {
        URL(string: Bundle.main.object(forInfoDictionaryKey: "APEXBaseURL") as? String ?? "") ?? URL(string: "http://localhost:8077")!
    }

    private static var cacheURL: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)?.appendingPathComponent("snapshot.json")
    }

    private static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 10
        c.waitsForConnectivity = false
        return URLSession(configuration: c)
    }()

    struct Result {
        let snapshot: WidgetSnapshot
        /// Non-nil when this came from disk because the network failed.
        let staleSince: Date?
    }

    static func snapshot(driver: String?, season: Int? = nil) async -> Result? {
        var url = baseURL.appending(path: "api/widgets/snapshot")
        if let driver { url.append(queryItems: [URLQueryItem(name: "driver", value: driver)]) }
        if let season { url.append(queryItems: [URLQueryItem(name: "season", value: String(season))]) }
        do {
            let (data, response) = try await session.data(from: url)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            let snap = try JSONDecoder.apex.decode(WidgetSnapshot.self, from: data)
            if let cacheURL { try? data.write(to: cacheURL, options: .atomic) }
            return Result(snapshot: snap, staleSince: nil)
        } catch {
            return cached()
        }
    }

    static func cached() -> Result? {
        guard let cacheURL, let data = try? Data(contentsOf: cacheURL),
              let snap = try? JSONDecoder.apex.decode(WidgetSnapshot.self, from: data) else { return nil }
        return Result(snapshot: snap, staleSince: snap.generatedAt)
    }

    static func drivers() async throws -> [DriverSummary] {
        let (data, _) = try await session.data(from: baseURL.appending(path: "api/drivers"))
        return try JSONDecoder.apex.decode([DriverSummary].self, from: data)
    }
}

/// Companion-app preferences, shared with the widget extension.
enum Prefs {
    static let defaults = UserDefaults(suiteName: APIClient.appGroup) ?? .standard

    static var driver: String? {
        get { defaults.string(forKey: "driver") }
        set { defaults.set(newValue, forKey: "driver") }
    }
    static var theme: Theme {
        get { Theme(rawValue: defaults.string(forKey: "theme") ?? "") ?? .dark }
        set { defaults.set(newValue.rawValue, forKey: "theme") }
    }
    static var accent: Accent {
        get { Accent(rawValue: defaults.string(forKey: "accent") ?? "") ?? .system }
        set { defaults.set(newValue.rawValue, forKey: "accent") }
    }
    static var density: Density {
        get { Density(rawValue: defaults.string(forKey: "density") ?? "") ?? .standard }
        set { defaults.set(newValue.rawValue, forKey: "density") }
    }
    static var teamColors: Bool {
        get { defaults.object(forKey: "teamColors") as? Bool ?? true }
        set { defaults.set(newValue, forKey: "teamColors") }
    }
}
