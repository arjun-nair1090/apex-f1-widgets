import SwiftUI
import WidgetKit

/// Resolved look for one entry: theme palette + accent + team-color switch.
struct Look {
    let p: Palette
    let accent: Color
    let teamColors: Bool

    init(_ e: APEXEntry, renderingMode: WidgetRenderingMode = .fullColor) {
        p = Palette.of(e.theme)
        switch e.accent {
        case .system: accent = e.theme == .light ? Tokens.signalOnLight : Tokens.signal
        case .team: accent = e.snapshot?.driver?.teamColor.map(Color.hex) ?? Tokens.signal
        case .red: accent = Tokens.motorsportRed
        }
        // Tinted / vibrant home screens: team colors become noise; glyphs carry the meaning.
        teamColors = e.teamColors && renderingMode == .fullColor
    }
}

private struct LookKey: EnvironmentKey {
    static let defaultValue = Look(.placeholder)
}

private struct FamilyKey: EnvironmentKey {
    static let defaultValue = WidgetFamily.systemMedium
}

extension EnvironmentValues {
    var look: Look {
        get { self[LookKey.self] }
        set { self[LookKey.self] = newValue }
    }

    /// WidgetKit's `widgetFamily` is read-only; this copy lets the companion app render the same views as previews.
    var apexFamily: WidgetFamily {
        get { self[FamilyKey.self] }
        set { self[FamilyKey.self] = newValue }
    }
}

/// `● LIVE · Q3`. Widgets can't run repeating animations, so the pulse lives in the app and Live Activity only.
struct LiveTag: View {
    var label: String? = nil
    @Environment(\.look) private var look

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(look.accent).frame(width: 6, height: 6)
            Text(label.map { "LIVE · \($0)" } ?? "LIVE").meta(look.accent)
        }
        .widgetAccentable()
        .accessibilityElement(children: .combine)
        .accessibilityLabel(label.map { "Live, \($0)" } ?? "Live")
    }
}

/// The apex rail (DESIGN_SYSTEM.md §5): 2px progress along the bottom edge.
struct Rail: View {
    enum Source { case fraction(Double), interval(ClosedRange<Date>) }
    let source: Source
    var on = false
    @Environment(\.look) private var look

    var body: some View {
        Group {
            switch source {
            case .fraction(let f):
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(look.p.border)
                        Capsule().fill(on ? look.accent : look.p.t1).frame(width: g.size.width * min(1, max(0, f)))
                    }
                }
            case .interval(let range):
                // Advances on its own between timeline entries.
                ProgressView(timerInterval: range, countsDown: false) { EmptyView() } currentValueLabel: { EmptyView() }
                    .progressViewStyle(.linear)
                    .tint(on ? look.accent : look.p.t1)
            }
        }
        .frame(height: Tokens.railHeight)
        .accessibilityHidden(true)
    }
}

struct Tick: View {
    let hex: String?
    @Environment(\.look) private var look

    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(look.teamColors ? hex.map(Color.hex) ?? .clear : .clear)
            .frame(width: 2, height: 11)
            .accessibilityHidden(true)
    }
}

struct RaceHeader: View {
    let race: Race?
    var trailing: String? = nil
    @Environment(\.look) private var look

    var body: some View {
        HStack(spacing: 6) {
            Text(Fmt.flag(race?.countryCode)).font(.system(size: 13)).accessibilityHidden(true)
            Text(race?.shortName ?? "").meta(look.p.t1)
            Spacer(minLength: 4)
            if let trailing { Text(trailing).meta(look.p.t3) }
        }
    }
}

/// "LAST UPDATED 2M AGO" when showing cached data (spec §23).
struct StaleLine: View {
    let e: APEXEntry
    @Environment(\.look) private var look

    var body: some View {
        if let since = e.staleSince, e.date.timeIntervalSince(since) > 60 {
            Text("Last updated \(Fmt.ago(since, now: e.date)) ago").micro(look.p.t3)
        }
    }
}

/// Countdown that ticks by itself: days are fixed per entry (entries exist at each day rollover), HH:MM:SS is a live timer.
struct Countdown: View {
    let target: Date
    let now: Date
    var font: Font = .apexDisplay

    var body: some View {
        let parts = Fmt.countdownParts(to: target, now: now)
        HStack(spacing: 8) {
            if parts.days > 0 { Text("\(parts.days)D") }
            if now < parts.dayBoundary {
                Text(timerInterval: now...parts.dayBoundary, countsDown: true, showsHours: true)
            } else {
                Text("00:00")
            }
        }
        .font(font)
        .monospacedDigit()
        .contentTransition(.numericText(countsDown: true))
    }
}

struct SectorGlyphs: View {
    let sectors: [String?]?

    var body: some View {
        HStack(spacing: 1) {
            ForEach(Array((sectors ?? []).enumerated()), id: \.offset) { _, s in
                switch s {
                case "purple": Text("◆").foregroundStyle(Tokens.sectorOverall)
                case "green": Text("▲").foregroundStyle(Tokens.sectorPersonal)
                case "yellow": Text("–").foregroundStyle(Tokens.sectorNone)
                default: Text("·").foregroundStyle(.secondary)
                }
            }
        }
        .font(.system(size: 9, weight: .bold))
        .accessibilityLabel(Text((sectors ?? []).map { $0 ?? "unknown" }.joined(separator: ", ")))
    }
}

struct TimingRowView: View {
    let row: TimingRow
    let timing: Timing
    var favourite = false
    var showSectors = false
    var showInterval = false
    @Environment(\.look) private var look

    var body: some View {
        HStack(spacing: 6) {
            Text("\(row.position)").foregroundStyle(look.p.t2).frame(width: 18, alignment: .trailing)
            Tick(hex: row.teamColor)
            Text(row.code).foregroundStyle(look.p.t1).frame(width: 34, alignment: .leading)
            Spacer(minLength: 0)
            if showSectors { SectorGlyphs(sectors: row.sectors) }
            value
            if showInterval, let i = row.interval { Text(i).foregroundStyle(look.p.t3) }
        }
        .font(.apexData)
        .monospacedDigit()
        .frame(height: 18)
        .background(alignment: .leading) {
            if favourite { Rectangle().fill(look.accent).frame(width: 2).offset(x: -16).widgetAccentable() }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var value: some View {
        if row.inPit {
            Text("PIT").font(.system(size: 10, weight: .semibold)).tracking(0.6)
                .padding(.horizontal, 4).padding(.vertical, 2)
                .overlay(RoundedRectangle(cornerRadius: 2).stroke(look.p.border))
                .transition(.push(from: .bottom))
        } else if row.position == 1 {
            Text(!timing.isRace || timing.final ? row.time ?? "" : "").foregroundStyle(look.p.t1)
        } else {
            Text(row.gap ?? "").foregroundStyle(look.p.t2).contentTransition(.numericText())
        }
    }
}

/// Visible rows; if the favourite is outside them the last row becomes `… 9 VER +21.4` (DESIGN_SYSTEM.md §8.4).
func visibleRows(_ t: Timing, count: Int, favourite: String?) -> [TimingRow] {
    var rows = Array(t.rows.prefix(count))
    if let fav = favourite, count > 2, !rows.contains(where: { $0.code == fav }), let f = t.rows.first(where: { $0.code == fav }) {
        rows = Array(rows.dropLast()) + [f]
    }
    return rows
}

/// Skeleton geometry matching real rows: no spinners (spec §35).
struct Skeleton: View {
    let rows: Int
    @Environment(\.look) private var look

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            RoundedRectangle(cornerRadius: 3).fill(look.p.elevated).frame(width: 64, height: 10)
            Spacer()
            ForEach(0..<rows, id: \.self) { i in
                RoundedRectangle(cornerRadius: 3).fill(look.p.elevated).frame(height: 10)
                    .padding(.trailing, CGFloat([20, 48, 32, 60][i % 4]))
            }
        }
        .redacted(reason: .placeholder)
        .accessibilityLabel("Loading")
    }
}
