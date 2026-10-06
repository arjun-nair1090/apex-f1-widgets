import Foundation

// Mirrors backend/apex/schemas.py (shared/api-schema/openapi.json). Decoded with .convertFromSnakeCase.

struct Session: Codable, Hashable, Identifiable {
    let id: String
    let round: Int
    let type: String
    let label: String
    let startsAt: Date
    let endsAt: Date
    let state: String
}

struct Race: Codable, Hashable {
    let season: Int
    let round: Int
    let name: String
    let shortName: String
    let circuitName: String
    let locality: String?
    let country: String?
    let countryCode: String?
    let lapsTotal: Int?
    let sessions: [Session]
}

struct DriverStanding: Codable, Hashable {
    let position: Int
    let driverId: String
    let code: String
    let name: String
    let teamId: String?
    let teamName: String?
    let teamColor: String?
    let points: Double
    let wins: Int
}

struct ConstructorStanding: Codable, Hashable {
    let position: Int
    let teamId: String
    let name: String
    let shortName: String
    let color: String?
    let points: Double
    let wins: Int
}

struct WeekendResult: Codable, Hashable {
    let sessionType: String
    let position: Int?
    let gap: String?
}

struct DriverDetail: Codable, Hashable {
    let id: String
    let code: String
    let number: Int?
    let firstName: String
    let lastName: String
    let countryCode: String?
    let teamId: String?
    let teamName: String?
    let teamColor: String?
    let position: Int?
    let points: Double
    let wins: Int
    let podiums: Int
    let poles: Int
    let last5: [Int?]
    let weekend: [WeekendResult]
}

struct DriverSummary: Codable, Hashable {
    let id: String
    let code: String
    let firstName: String
    let lastName: String
    let teamName: String?
}

struct TimingRow: Codable, Hashable {
    let position: Int
    let driverNumber: Int
    let code: String
    let teamColor: String?
    let time: String?
    let gap: String?
    let interval: String?
    let sectors: [String?]?
    let inPit: Bool
    let drs: Bool?
}

struct Timing: Codable, Hashable {
    let sessionId: String
    let sessionType: String
    let phase: String?
    let lap: Int?
    let lapsTotal: Int?
    let final: Bool
    let updatedAt: Date
    let rows: [TimingRow]

    var isRace: Bool { sessionType == "RACE" || sessionType == "SPRINT" }
}

struct WidgetSnapshot: Codable, Hashable {
    let generatedAt: Date
    let mode: String
    let race: Race?
    let nextSession: Session?
    let live: Timing?
    let results: Timing?
    let drivers: [DriverStanding]
    let constructors: [ConstructorStanding]
    let driver: DriverDetail?
    let liveUnavailable: Bool
}

extension JSONDecoder {
    static let apex: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let frac = ISO8601DateFormatter()
        frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        d.dateDecodingStrategy = .custom { decoder in
            let s = try decoder.singleValueContainer().decode(String.self)
            if let date = frac.date(from: s) ?? plain.date(from: s) { return date }
            // Python emits microseconds; trim to milliseconds for ISO8601DateFormatter.
            let trimmed = s.replacingOccurrences(of: #"(\.\d{3})\d+"#, with: "$1", options: .regularExpression)
            if let date = frac.date(from: trimmed) { return date }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Bad date \(s)"))
        }
        return d
    }()
}
