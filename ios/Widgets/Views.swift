import SwiftUI
import WidgetKit

// One view per widget; each has a layout per family, never a scaled one (spec §27).

struct RaceModeView: View {
    let e: APEXEntry

    var body: some View {
        switch e.mode {
        case .live: TimingView(e: e, results: false)
        case .results: TimingView(e: e, results: true)
        case .countdown: CountdownView(e: e, target: e.nextSession)
        case .next: NextSessionView(e: e)
        }
    }
}

// MARK: Next session

struct NextSessionView: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    var body: some View {
        if let s = e.nextSession {
            if RaceMode.state(s, at: e.date) == "live" {
                TimingView(e: e, results: false)
            } else {
                content(s)
            }
        } else {
            VStack(alignment: .leading) {
                Text("Season complete").meta(look.p.t2)
                Spacer()
                Text("See you next year").font(.apexTitle).foregroundStyle(look.p.t1)
            }
        }
    }

    private func content(_ s: Session) -> some View {
        let soon = RaceMode.state(s, at: e.date) == "starting_soon"
        let rail = previousEnd(before: s).map { Rail(source: .interval($0...s.startsAt)) }
        return VStack(alignment: .leading, spacing: 0) {
            switch family {
            case .systemSmall:
                HStack(spacing: 6) {
                    Text(Fmt.flag(e.snapshot?.race?.countryCode)).font(.system(size: 13))
                    Text(e.snapshot?.race?.shortName.replacingOccurrences(of: " GP", with: "") ?? "").meta(look.p.t1)
                }
                Spacer()
                Text(s.label).meta(look.p.t1)
                Text(Fmt.dayTime(s.startsAt)).meta(look.p.t3).padding(.top, 4)
                Countdown(target: s.startsAt, now: e.date, font: .apexBig)
                    .fontWeight(soon ? .bold : .semibold).foregroundStyle(look.p.t1).padding(.top, 12)
            default:
                RaceHeader(race: e.snapshot?.race, trailing: soon ? "◐ SOON" : "R\(e.snapshot?.race?.round ?? 0)")
                if family == .systemLarge {
                    WeekendList(e: e).padding(.top, 20)
                    Text(e.snapshot?.race?.circuitName ?? "").micro(look.p.t3).padding(.top, 12)
                }
                Spacer()
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(Fmt.title(s.label)).font(.apexTitle).foregroundStyle(look.p.t1)
                        Text(Fmt.dayTime(s.startsAt)).meta(look.p.t3)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 6) {
                        Text("Starts in").meta(look.p.t3)
                        Countdown(target: s.startsAt, now: e.date, font: family == .systemLarge ? .apexHero : .apexDisplay)
                            .fontWeight(soon ? .bold : .semibold).foregroundStyle(look.p.t1)
                    }
                }
            }
            StaleLine(e: e)
        }
        .padding(.bottom, 6)
        .overlay(alignment: .bottom) { rail }
    }

    private func previousEnd(before s: Session) -> Date? {
        let prev = e.snapshot?.race?.sessions.filter { $0.endsAt <= s.startsAt }.map(\.endsAt).max()
        let from = prev ?? s.startsAt.addingTimeInterval(-7 * 86400)
        return from < s.startsAt ? from : nil
    }
}

// MARK: Countdown

struct CountdownView: View {
    let e: APEXEntry
    /// nil = this weekend's race.
    var target: Session? = nil
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    private var session: Session? { target ?? e.snapshot?.race?.sessions.first { $0.type == "RACE" } }

    var body: some View {
        if let s = session, RaceMode.state(s, at: e.date) == "live" || RaceMode.state(s, at: e.date) == "finished" {
            // LIVE at lights out, without a refresh (spec §8). AnyView breaks the
            // RaceModeView → CountdownView → RaceModeView opaque-type cycle.
            AnyView(RaceModeView(e: e))
        } else if let s = session {
            content(s)
        } else {
            NextSessionView(e: e)
        }
    }

    private func content(_ s: Session) -> some View {
        let name = Fmt.sessionShort(s.type)
        let parts = Fmt.countdownParts(to: s.startsAt, now: e.date)
        return VStack(alignment: .leading, spacing: 0) {
            switch family {
            case .accessoryRectangular:
                Text("\(name) · \(e.snapshot?.race?.shortName ?? "")").font(.system(size: 12, weight: .semibold)).textCase(.uppercase)
                Countdown(target: s.startsAt, now: e.date, font: .system(size: 22, weight: .semibold, design: .monospaced))
                Text(Fmt.dayTime(s.startsAt)).font(.system(size: 12, design: .monospaced)).foregroundStyle(.secondary)
            case .accessoryCircular:
                VStack(spacing: 0) {
                    Text(parts.days > 0 ? "DAYS" : "HRS").font(.system(size: 9, weight: .semibold))
                    Text(parts.days > 0 ? "\(parts.days)" : "\(Int(s.startsAt.timeIntervalSince(e.date) / 3600))")
                        .font(.system(size: 20, weight: .semibold, design: .monospaced))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(AccessoryWidgetBackground())
            case .systemSmall:
                Text("\(name) in").meta(look.p.t2)
                Spacer()
                if parts.days > 0 {
                    Text(Fmt.pad(parts.days)).font(.apexDisplay).foregroundStyle(look.p.t1)
                    Text("Days").micro(look.p.t3).padding(.top, 4).padding(.bottom, 10)
                }
                Text(timerInterval: e.date...max(e.date, parts.dayBoundary), countsDown: true, showsHours: true)
                    .font(parts.days > 0 ? .apexBig : .apexDisplay).monospacedDigit().foregroundStyle(look.p.t1)
            case .systemMedium:
                HStack {
                    Text("\(name) starts in").meta(look.p.t2)
                    Spacer()
                    Text(Fmt.flag(e.snapshot?.race?.countryCode)).font(.system(size: 13))
                    Text(e.snapshot?.race?.shortName ?? "").meta(look.p.t1)
                }
                HStack { Spacer(); Text(Fmt.dayTime(s.startsAt)).meta(look.p.t3) }.padding(.top, 4)
                Spacer()
                HStack(alignment: .bottom, spacing: 20) {
                    if parts.days > 0 {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(Fmt.pad(parts.days)).font(.apexHero).foregroundStyle(look.p.t1)
                            Text("Days").micro(look.p.t3)
                        }
                    }
                    Text(timerInterval: e.date...max(e.date, parts.dayBoundary), countsDown: true, showsHours: true)
                        .font(.apexHero).monospacedDigit()
                        .foregroundStyle(parts.days > 0 ? look.p.t2 : look.p.t1)
                        .padding(.bottom, parts.days > 0 ? 15 : 0)
                }
            default:
                RaceHeader(race: e.snapshot?.race, trailing: "R\(e.snapshot?.race?.round ?? 0)")
                Spacer()
                Text("\(name) starts in").meta(look.p.t2)
                if parts.days > 0 {
                    Text(Fmt.pad(parts.days)).font(.system(size: 96, weight: .semibold, design: .monospaced))
                        .foregroundStyle(look.p.t1).padding(.top, 12)
                    Text("Days").micro(look.p.t3).padding(.top, 6).padding(.bottom, 16)
                }
                Text(timerInterval: e.date...max(e.date, parts.dayBoundary), countsDown: true, showsHours: true)
                    .font(parts.days > 0 ? .apexHero : .system(size: 64, weight: .semibold, design: .monospaced))
                    .monospacedDigit().foregroundStyle(look.p.t1)
                Spacer()
                Text("\(Fmt.dayTime(s.startsAt)) · \(e.snapshot?.race?.circuitName ?? "")").meta(look.p.t3)
            }
            if !family.isAccessory { StaleLine(e: e) }
        }
        .padding(.bottom, family.isAccessory ? 0 : 6)
        .accessibilityElement(children: .combine)
    }
}

// MARK: Live timing / results

struct TimingView: View {
    let e: APEXEntry
    let results: Bool
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    var body: some View {
        if let t = results ? e.snapshot?.results : e.snapshot?.live {
            content(t)
        } else {
            EmptyLiveView(e: e)
        }
    }

    private var favourite: String? { e.snapshot?.driver?.code }

    private func content(_ t: Timing) -> some View {
        let label = t.phase ?? Fmt.sessionShort(t.sessionType)
        let progress: Rail? = t.final ? nil : t.lap.flatMap { lap in t.lapsTotal.map { Rail(source: .fraction(Double(lap) / Double($0)), on: true) } }
            ?? e.snapshot?.race?.sessions.first { $0.id == t.sessionId }.map { Rail(source: .interval($0.startsAt...$0.endsAt), on: true) }
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                if t.final { Text("✓ Final · \(label)").meta(look.p.t1) } else { LiveTag(label: family == .systemSmall ? nil : label) }
                Spacer()
                if let lap = t.lap {
                    Text(family == .systemSmall || t.lapsTotal == nil ? "L\(lap)" : "L\(lap) / \(t.lapsTotal!)")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced)).foregroundStyle(look.p.t1)
                }
            }
            switch family {
            case .systemSmall:
                Spacer()
                if let p1 = t.rows.first {
                    Text("P\(p1.position)").font(.apexDisplay).foregroundStyle(look.p.t1)
                    HStack(spacing: 6) { Tick(hex: p1.teamColor); Text(p1.code).font(.apexTitle).foregroundStyle(look.p.t1) }.padding(.top, 6)
                    if !t.isRace, let time = p1.time { Text(time).font(.apexData).foregroundStyle(look.p.t3).padding(.top, 6) }
                }
            case .systemMedium:
                Spacer()
                let rows = visibleRows(t, count: e.density == .minimal ? 3 : 6, favourite: favourite)
                if rows.count > 3 {
                    HStack(alignment: .top, spacing: 20) {
                        column(Array(rows.prefix(3)), t)
                        column(Array(rows.dropFirst(3)), t)
                    }
                } else {
                    column(rows, t)
                }
            default:
                RaceHeader(race: e.snapshot?.race).padding(.top, 6)
                Spacer()
                column(visibleRows(t, count: e.density == .minimal ? 6 : e.density == .detailed ? 12 : 10, favourite: favourite), t,
                       sectors: e.density != .minimal, interval: e.density == .detailed)
            }
            StaleLine(e: e)
        }
        .padding(.bottom, 6)
        .overlay(alignment: .bottom) { progress }
        .widgetURL(URL(string: "apex://timing"))
        .animation(.spring(response: 0.35, dampingFraction: 0.86), value: t.rows.map(\.code))
    }

    private func column(_ rows: [TimingRow], _ t: Timing, sectors: Bool = false, interval: Bool = false) -> some View {
        VStack(spacing: 4) {
            ForEach(rows, id: \.code) { r in
                TimingRowView(row: r, timing: t, favourite: r.code == favourite, showSectors: sectors, showInterval: interval)
            }
        }
    }
}

/// Spec §33 (no live session) and §34 (live data unavailable).
struct EmptyLiveView: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if e.mode == .live {
                // Lights out happened after the last fetch, or the live feed is down.
                LiveTag(label: e.nextSession.map { Fmt.sessionShort($0.type) })
                Spacer()
                if e.snapshot?.liveUnavailable == true {
                    Text("Live data unavailable").meta(look.p.t1)
                    if family != .systemSmall {
                        Text("Using cached data · updated \(Fmt.ago(e.staleSince ?? e.snapshot?.generatedAt ?? e.date, now: e.date).lowercased()) ago")
                            .font(.system(size: 13)).foregroundStyle(look.p.t2).padding(.top, 6)
                    }
                    Button(intent: RefreshIntent()) { Text("Retry").font(.system(size: 11, weight: .semibold)) }
                        .buttonStyle(.bordered).tint(look.p.t1).padding(.top, 12)
                } else {
                    Text(e.snapshot?.race?.shortName ?? "").meta(look.p.t1)
                    Text("Timing is on its way").font(.system(size: 13)).foregroundStyle(look.p.t2).padding(.top, 6)
                }
            } else if let s = e.nextSession {
                HStack {
                    Text("No live session").meta(look.p.t2)
                    Spacer()
                    if family != .systemSmall { RaceHeader(race: e.snapshot?.race).fixedSize() }
                }
                Spacer()
                if family != .systemSmall { Text("Next session").micro(look.p.t3).padding(.bottom, 8) }
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(s.label).meta(look.p.t1)
                        Text(Fmt.dayTime(s.startsAt)).meta(look.p.t3)
                    }
                    if family != .systemSmall {
                        Spacer()
                        Countdown(target: s.startsAt, now: e.date).foregroundStyle(look.p.t1)
                    }
                }
                if family == .systemSmall {
                    Countdown(target: s.startsAt, now: e.date, font: .apexBig).foregroundStyle(look.p.t1).padding(.top, 10)
                }
            } else {
                Text("No live session").meta(look.p.t2)
            }
            StaleLine(e: e)
        }
    }
}

// MARK: Driver

struct DriverView: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    var body: some View {
        if let d = e.snapshot?.driver {
            content(d)
        } else {
            ChooseDriver()
        }
    }

    private func content(_ d: DriverDetail) -> some View {
        let pos = d.position.map { "P\($0)" } ?? "—"
        return VStack(alignment: .leading, spacing: 0) {
            switch family {
            case .systemSmall:
                HStack(spacing: 6) { Text(Fmt.flag(d.countryCode)); Text(d.teamName ?? "").meta(look.p.t2) }
                Spacer()
                Text(pos).font(.apexDisplay).foregroundStyle(look.p.t1)
                HStack(spacing: 6) { Tick(hex: d.teamColor); Text(d.code).font(.apexTitle).foregroundStyle(look.p.t1) }.padding(.top, 6)
                Text("\(Fmt.points(d.points)) PTS").font(.apexData).foregroundStyle(look.p.t3).padding(.top, 6)
            default:
                HStack(spacing: 6) {
                    Tick(hex: d.teamColor)
                    Text("\(d.firstName) \(d.lastName)").font(.system(size: 15, weight: .semibold)).textCase(.uppercase).foregroundStyle(look.p.t1)
                    Spacer()
                    Text(Fmt.flag(d.countryCode))
                    Text(d.teamName ?? "").meta(look.p.t2)
                }
                Spacer()
                HStack(alignment: .lastTextBaseline) {
                    Text(pos).font(family == .systemLarge ? .system(size: 72, weight: .semibold, design: .monospaced) : .apexHero)
                    Spacer()
                    Text(Fmt.points(d.points)).font(.apexBig)
                    Text("PTS").meta(look.p.t3)
                }
                .foregroundStyle(look.p.t1)
                if e.showStats {
                    HStack(spacing: 16) {
                        stat("Wins", d.wins); stat("Podiums", d.podiums); stat("Poles", d.poles)
                    }
                    .padding(.top, 14)
                }
                if family == .systemLarge, e.showLast5, !d.last5.isEmpty {
                    Text("Last \(d.last5.count)").micro(look.p.t3).padding(.top, 20)
                    LastFive(results: d.last5).padding(.top, 8)
                }
            }
            StaleLine(e: e)
        }
        .accessibilityElement(children: .combine)
    }

    private func stat(_ label: String, _ value: Int) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).micro(look.p.t3)
            Text("\(value)").font(.system(size: 15, weight: .semibold, design: .monospaced)).foregroundStyle(look.p.t1)
        }
    }
}

struct LastFive: View {
    let results: [Int?]
    @Environment(\.look) private var look

    var body: some View {
        HStack(spacing: 10) {
            ForEach(Array(results.enumerated()), id: \.offset) { i, p in
                Text(p.map { "P\($0)" } ?? "DNF").foregroundStyle(i == 0 ? look.p.t1 : look.p.t2)
            }
        }
        .font(.apexData)
    }
}

struct ChooseDriver: View {
    @Environment(\.look) private var look

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Driver").meta(look.p.t2)
            Spacer()
            Text("Choose a driver").font(.apexTitle).foregroundStyle(look.p.t1)
            Text("Touch and hold, then Edit Widget.").font(.system(size: 13)).foregroundStyle(look.p.t2)
        }
    }
}

// MARK: Favourite driver (smart, spec §14)

struct FavouriteView: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    private struct Moment { let label: String; let live: Bool; let big: String; let top: String; let sub: String; let pit: Bool }

    private func moment(_ d: DriverDetail) -> Moment {
        if e.mode == .live, let t = e.snapshot?.live, let r = t.rows.first(where: { $0.code == d.code }) {
            let sub = r.position == 1 ? (t.isRace ? "LEADER" : r.time ?? "") : r.gap ?? ""
            return Moment(label: t.phase ?? Fmt.sessionShort(t.sessionType), live: true, big: "P\(r.position)",
                          top: t.lap.map { "L\($0)" } ?? "", sub: sub, pit: r.inPit)
        }
        if let race = d.weekend.first(where: { $0.sessionType == "RACE" && $0.position != nil }) {
            return Moment(label: "✓ Race", live: false, big: "P\(race.position!)", top: "",
                          sub: race.gap ?? (race.position == 1 ? "WINNER" : ""), pit: false)
        }
        if let q = d.weekend.first(where: { $0.sessionType == "QUALIFYING" && $0.position != nil }) {
            return Moment(label: "Grid", live: false, big: "QUALI P\(q.position!)", top: "", sub: "", pit: false)
        }
        return Moment(label: "Championship", live: false, big: d.position.map { "P\($0)" } ?? "—", top: "",
                      sub: "\(Fmt.points(d.points)) PTS", pit: false)
    }

    var body: some View {
        if let d = e.snapshot?.driver {
            let m = moment(d)
            VStack(alignment: .leading, spacing: 0) {
                if family == .accessoryRectangular {
                    Text(m.live ? "● \(m.label)" : m.label).font(.system(size: 12, weight: .semibold)).textCase(.uppercase)
                    Text("\(m.big) \(d.code)").font(.system(size: 22, weight: .semibold, design: .monospaced))
                    Text(m.pit ? "PIT" : [m.top, m.sub].filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(.system(size: 12, design: .monospaced)).foregroundStyle(.secondary)
                } else {
                    HStack {
                        if m.live { LiveTag(label: m.label) } else { Text(m.label).meta(look.p.t2) }
                        Spacer()
                        if family != .systemSmall { Text("\(d.firstName) \(d.lastName)").meta(look.p.t1) }
                    }
                    Spacer()
                    HStack(alignment: .lastTextBaseline) {
                        Text(m.big).font(m.big.count > 4 ? .apexBig : family == .systemSmall ? .apexDisplay : .apexHero)
                            .contentTransition(.numericText())
                        Spacer()
                        Text(m.top).font(.system(size: 11, weight: .semibold, design: .monospaced))
                    }
                    .foregroundStyle(look.p.t1)
                    HStack(spacing: 6) {
                        Tick(hex: d.teamColor)
                        Text(d.code).font(.apexTitle).foregroundStyle(look.p.t1)
                        Spacer()
                        if m.pit {
                            Text("PIT").font(.system(size: 10, weight: .semibold)).padding(.horizontal, 4).padding(.vertical, 2)
                                .overlay(RoundedRectangle(cornerRadius: 2).stroke(look.p.border))
                        } else {
                            Text(m.sub).font(.apexData).foregroundStyle(look.p.t2)
                        }
                    }
                    .padding(.top, 6)
                    StaleLine(e: e)
                }
            }
            .accessibilityElement(children: .combine)
        } else {
            ChooseDriver()
        }
    }
}

// MARK: Championships

struct StandingsView: View {
    enum Kind { case drivers, constructors }
    let e: APEXEntry
    let kind: Kind
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    private struct Line: Hashable { let pos: Int; let name: String; let color: String?; let points: Double; let fav: Bool }

    private var lines: [Line] {
        guard let s = e.snapshot else { return [] }
        let favCode = e.snapshot?.driver?.code, favTeam = e.snapshot?.driver?.teamId
        let all: [Line] = kind == .drivers
            ? s.drivers.map { Line(pos: $0.position, name: $0.code, color: $0.teamColor, points: $0.points, fav: $0.code == favCode) }
            : s.constructors.map { Line(pos: $0.position, name: $0.shortName, color: $0.color, points: $0.points, fav: $0.teamId == favTeam) }
        let n = family == .systemSmall ? 3 : family == .systemMedium ? (e.density == .minimal ? 3 : 5) : (e.density == .minimal ? 6 : 10)
        var shown = Array(all.prefix(n))
        if !shown.contains(where: \.fav) {
            // Favourite outside the top N (or outside the API's top 10): replace the last row.
            let fav = all.first(where: \.fav) ?? (kind == .drivers ? e.snapshot?.driver.flatMap { d in
                d.position.map { Line(pos: $0, name: d.code, color: d.teamColor, points: d.points, fav: true) } } : nil)
            if let fav, n > 2 { shown = Array(shown.dropLast()) + [fav] }
        }
        return shown
    }

    var body: some View {
        let leader = e.snapshot?.drivers.first?.points ?? 0
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(kind == .drivers ? "WDC" : "WCC").meta(look.p.t1)
                Spacer()
                if family != .systemSmall, let r = e.snapshot?.race?.round { Text("After R\(max(1, r - 1))").meta(look.p.t3) }
            }
            Spacer()
            VStack(spacing: 4) {
                ForEach(lines, id: \.self) { l in
                    HStack(spacing: 6) {
                        Text(Fmt.pad(l.pos)).foregroundStyle(look.p.t2).frame(width: 18, alignment: .trailing)
                        Tick(hex: l.color)
                        Text(l.name).font(kind == .drivers ? .apexData : .system(size: 12, weight: .semibold)).tracking(kind == .drivers ? 0 : 0.5)
                        Spacer()
                        if family == .systemLarge, e.density == .detailed, kind == .drivers, l.pos > 1 {
                            Text("−\(Fmt.points(leader - l.points))").foregroundStyle(look.p.t3).padding(.trailing, 12)
                        }
                        Text(Fmt.points(l.points))
                    }
                    .font(.apexData).monospacedDigit().foregroundStyle(look.p.t1).frame(height: 18)
                    .background(alignment: .leading) {
                        if l.fav { Rectangle().fill(look.accent).frame(width: 2).offset(x: -16) }
                    }
                }
            }
            StaleLine(e: e)
        }
    }
}

// MARK: Race weekend

struct WeekendList: View {
    let e: APEXEntry
    @Environment(\.look) private var look

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 4) {
            ForEach(e.snapshot?.race?.sessions ?? []) { s in
                let st = RaceMode.state(s, at: e.date)
                let color = st == "finished" ? look.p.t3 : st == "live" ? look.accent : look.p.t1
                GridRow {
                    Text(Fmt.day(s.startsAt)).font(.system(size: 10, weight: .semibold)).tracking(0.7).foregroundStyle(look.p.t3)
                    Text(s.label).font(.system(size: 13, weight: .semibold)).foregroundStyle(color)
                    Text(st == "finished" ? "✓" : st == "live" ? "●" : st == "starting_soon" ? "◐" : "○")
                        .font(.system(size: 13, design: .monospaced)).foregroundStyle(color)
                        .accessibilityLabel(st.replacingOccurrences(of: "_", with: " "))
                    Group {
                        if st == "live" { Text("LIVE").foregroundStyle(look.accent) }
                        else if st != "finished" { Text(Fmt.hhmm(s.startsAt)).foregroundStyle(look.p.t2) }
                        else { Text("") }
                    }
                    .font(.system(size: 12, design: .monospaced)).gridColumnAlignment(.trailing)
                }
            }
        }
    }
}

struct WeekendView: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family
    @Environment(\.look) private var look

    var body: some View {
        if let race = e.snapshot?.race {
            VStack(alignment: .leading, spacing: 0) {
                if family == .systemSmall {
                    HStack(spacing: 6) { Text(Fmt.flag(race.countryCode)); Text(race.shortName.replacingOccurrences(of: " GP", with: "")).meta(look.p.t1) }
                    HStack(spacing: 6) {
                        ForEach(race.sessions) { s in
                            let st = RaceMode.state(s, at: e.date)
                            Text(st == "finished" ? "✓" : st == "live" ? "●" : "○")
                                .foregroundStyle(st == "live" ? look.accent : st == "finished" ? look.p.t3 : look.p.t1)
                        }
                    }
                    .font(.system(size: 15, design: .monospaced)).padding(.top, 14)
                    Spacer()
                    if let s = e.nextSession {
                        let live = RaceMode.state(s, at: e.date) == "live"
                        Text(live ? "● \(s.label)" : s.label).meta(live ? look.accent : look.p.t1)
                        Text(live ? "Live now" : Fmt.dayTime(s.startsAt)).meta(look.p.t3).padding(.top, 4)
                    }
                } else {
                    RaceHeader(race: race, trailing: "R\(race.round)")
                    if family == .systemMedium { Spacer() }
                    WeekendList(e: e).padding(.top, family == .systemLarge ? 20 : 0)
                    if family == .systemLarge {
                        Text(race.circuitName).micro(look.p.t3).padding(.top, 16)
                        Spacer()
                        if let s = e.nextSession, RaceMode.state(s, at: e.date) != "live" {
                            HStack(alignment: .bottom) {
                                VStack(alignment: .leading, spacing: 6) { Text("Next").micro(look.p.t3); Text(s.label).font(.apexTitle) }
                                Spacer()
                                Countdown(target: s.startsAt, now: e.date)
                            }
                            .foregroundStyle(look.p.t1)
                        }
                    }
                }
                StaleLine(e: e)
            }
        } else {
            Text("No upcoming weekend").meta(look.p.t2)
        }
    }
}

// MARK: Lock screen (Race Mode accessory families)

struct LockScreenView: View {
    let e: APEXEntry
    @Environment(\.apexFamily) private var family

    var body: some View {
        let live = e.mode == .live ? e.snapshot?.live : nil
        switch family {
        case .accessoryInline:
            if let t = live, let p1 = t.rows.first {
                Text("● \(p1.code) leads\(t.lap.map { " · L\($0)" } ?? "")")
            } else if let s = e.nextSession {
                Text("\(Fmt.sessionShort(s.type)) \(Fmt.dayTime(s.startsAt))")
            }
        case .accessoryCircular:
            if let t = live {
                VStack(spacing: 0) {
                    Text("LAP").font(.system(size: 9, weight: .semibold))
                    Text(t.lap.map { "\($0)" } ?? "—").font(.system(size: 18, weight: .semibold, design: .monospaced))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity).background(AccessoryWidgetBackground())
            } else {
                CountdownView(e: e, target: e.nextSession)
            }
        default:
            if let t = live {
                VStack(alignment: .leading, spacing: 2) {
                    Text("● LIVE · \(t.phase ?? Fmt.sessionShort(t.sessionType))\(t.lap.map { " · L\($0)" } ?? "")")
                        .font(.system(size: 12, weight: .semibold))
                    Text("\(t.rows.first?.code ?? "") \(t.rows.dropFirst().first?.gap ?? "")")
                        .font(.system(size: 22, weight: .semibold, design: .monospaced))
                    Text(t.rows.prefix(3).map(\.code).joined(separator: " ")).font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            } else {
                CountdownView(e: e, target: e.nextSession)
            }
        }
    }
}

extension WidgetFamily {
    var isAccessory: Bool { self == .accessoryCircular || self == .accessoryRectangular || self == .accessoryInline }
}
