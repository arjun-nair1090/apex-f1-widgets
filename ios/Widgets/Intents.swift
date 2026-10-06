import AppIntents
import WidgetKit

struct DriverEntity: AppEntity {
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Driver"
    static let defaultQuery = DriverQuery()
    let id: String
    let name: String
    let team: String?

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)", subtitle: team.map { "\($0)" })
    }
}

struct DriverQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [DriverEntity] {
        try await suggestedEntities().filter { identifiers.contains($0.id) }
    }

    func suggestedEntities() async throws -> [DriverEntity] {
        try await APIClient.drivers().map {
            DriverEntity(id: $0.id, name: "\($0.firstName) \($0.lastName)", team: $0.teamName)
        }
    }
}

enum DensityOption: String, AppEnum {
    case minimal, standard, detailed
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Information"
    static let caseDisplayRepresentations: [DensityOption: DisplayRepresentation] = [
        .minimal: "Minimal", .standard: "Standard", .detailed: "Detailed",
    ]
    var density: Density { Density(rawValue: rawValue) ?? .standard }
}

/// Shared by every APEX widget: favourite driver + information density.
struct APEXConfigIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "APEX widget"
    static let description = IntentDescription("Choose your driver and how much to show.")

    @Parameter(title: "Driver") var driver: DriverEntity?
    @Parameter(title: "Information", default: .standard) var density: DensityOption
}

/// Driver widget adds season and which stats appear (spec §10).
struct DriverConfigIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "Driver"
    static let description = IntentDescription("Your driver's season at a glance.")

    @Parameter(title: "Driver") var driver: DriverEntity?
    @Parameter(title: "Season", description: "Leave empty for the current season") var season: Int?
    @Parameter(title: "Show wins, podiums, poles", default: true) var showStats: Bool
    @Parameter(title: "Show last 5 results", default: true) var showLast5: Bool
}

/// Interactive "Retry" on the error state (spec §34).
struct RefreshIntent: AppIntent {
    static let title: LocalizedStringResource = "Refresh"
    func perform() async throws -> some IntentResult {
        WidgetCenter.shared.reloadAllTimelines()
        return .result()
    }
}
