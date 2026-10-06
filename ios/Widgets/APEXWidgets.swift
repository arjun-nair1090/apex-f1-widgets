import SwiftUI
import WidgetKit

@main
struct APEXWidgets: WidgetBundle {
    var body: some Widget {
        RaceModeWidget()
        NextSessionWidget()
        CountdownWidget()
        LiveTimingWidget()
        DriverWidget()
        FavouriteDriverWidget()
        DriverChampionshipWidget()
        ConstructorChampionshipWidget()
        RaceWeekendWidget()
        RaceLiveActivity()
    }
}

/// Theme, accent and container for every widget.
struct WidgetShell<Content: View>: View {
    let e: APEXEntry
    @ViewBuilder let content: Content
    @Environment(\.widgetRenderingMode) private var renderingMode
    @Environment(\.widgetFamily) private var family

    var body: some View {
        let look = Look(e, renderingMode: renderingMode)
        Group {
            if e.snapshot == nil && !family.isAccessory {
                Skeleton(rows: family == .systemSmall ? 2 : family == .systemMedium ? 3 : 9)
            } else {
                content
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .environment(\.look, look)
        .environment(\.apexFamily, family)
        .containerBackground(for: .widget) { look.p.surface }
    }
}

private let homeFamilies: [WidgetFamily] = [.systemSmall, .systemMedium, .systemLarge]

struct RaceModeWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.racemode", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { RaceModeFamilies(e: e) }
        }
        .configurationDisplayName("APEX")
        .description("Shows what matters now: countdown, live timing, results or the next session.")
        .supportedFamilies(homeFamilies + [.accessoryRectangular, .accessoryCircular, .accessoryInline])
    }
}

private struct RaceModeFamilies: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family

    var body: some View {
        if family.isAccessory { LockScreenView(e: e) } else { RaceModeView(e: e) }
    }
}

struct NextSessionWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.next", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { NextSessionView(e: e) }
        }
        .configurationDisplayName("Next session")
        .description("What's next, and when.")
        .supportedFamilies(homeFamilies)
    }
}

struct CountdownWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.countdown", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { CountdownView(e: e) }
        }
        .configurationDisplayName("Countdown")
        .description("How long until lights out. Switches to live timing at the start.")
        .supportedFamilies(homeFamilies + [.accessoryRectangular, .accessoryCircular])
    }
}

struct LiveTimingWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.timing", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { TimingView(e: e, results: e.mode == .results) }
        }
        .configurationDisplayName("Live timing")
        .description("Who's leading, and by how much.")
        .supportedFamilies(homeFamilies)
    }
}

struct DriverWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.driver", intent: DriverConfigIntent.self, provider: DriverProvider()) { e in
            WidgetShell(e: e) { DriverView(e: e) }
        }
        .configurationDisplayName("Driver")
        .description("Your driver's season at a glance.")
        .supportedFamilies(homeFamilies)
    }
}

struct FavouriteDriverWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.favourite", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { FavouriteView(e: e) }
        }
        .configurationDisplayName("Favourite driver")
        .description("Live position, result, grid slot or title standing: whichever matters now.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}

struct DriverChampionshipWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.wdc", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { StandingsView(e: e, kind: .drivers) }
        }
        .configurationDisplayName("Drivers' championship")
        .description("The title fight, with your driver highlighted.")
        .supportedFamilies(homeFamilies)
    }
}

struct ConstructorChampionshipWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.wcc", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { StandingsView(e: e, kind: .constructors) }
        }
        .configurationDisplayName("Constructors' championship")
        .description("Team standings, with your driver's team highlighted.")
        .supportedFamilies(homeFamilies)
    }
}

struct RaceWeekendWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "apex.weekend", intent: APEXConfigIntent.self, provider: APEXProvider()) { e in
            WidgetShell(e: e) { WeekendView(e: e) }
        }
        .configurationDisplayName("Race weekend")
        .description("Every session this weekend.")
        .supportedFamilies(homeFamilies)
    }
}
