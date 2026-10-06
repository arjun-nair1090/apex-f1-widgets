import ActivityKit
import SwiftUI
import WidgetKit

/// Lock Screen banner + Dynamic Island while a session is live.
struct RaceLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RaceActivityAttributes.self) { context in
            LockScreenBanner(context: context)
                .padding(16)
                .activityBackgroundTint(Palette.of(.dark).surface)
                .activitySystemActionForegroundColor(Palette.of(.dark).t1)
        } dynamicIsland: { context in
            let s = context.state
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    LiveDot(label: s.phase)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if let lap = s.lap {
                        Text("L\(lap)\(s.lapsTotal.map { " / \($0)" } ?? "")")
                            .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 4) {
                        ForEach(s.top, id: \.code) { CarRow(car: $0, favourite: $0.code == s.favourite?.code) }
                        if let f = s.favourite, !s.top.contains(f) { CarRow(car: f, favourite: true) }
                    }
                    .padding(.top, 4)
                }
            } compactLeading: {
                HStack(spacing: 4) {
                    Circle().fill(Tokens.signal).frame(width: 6, height: 6)
                    Text(s.favourite.map { "P\($0.position)" } ?? s.top.first?.code ?? "")
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                }
            } compactTrailing: {
                Text(s.favourite.map { $0.inPit ? "PIT" : $0.code } ?? s.lap.map { "L\($0)" } ?? "")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
            } minimal: {
                Text(s.favourite.map { "\($0.position)" } ?? "●")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Tokens.signal)
            }
            .widgetURL(URL(string: "apex://timing"))
            .keylineTint(Tokens.signal)
        }
    }
}

/// The one ambient animation in the product: a 2 s opacity pulse, off with Reduce Motion (DESIGN_SYSTEM.md §6).
struct LiveDot: View {
    let label: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var dim = false

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(Tokens.signal).frame(width: 6, height: 6)
                .opacity(dim ? 0.45 : 1)
                .onAppear {
                    guard !reduceMotion else { return }
                    withAnimation(.easeInOut(duration: 1).repeatForever(autoreverses: true)) { dim = true }
                }
            Text("LIVE · \(label)").font(.system(size: 11, weight: .semibold)).tracking(0.8).foregroundStyle(Tokens.signal)
        }
    }
}

private struct CarRow: View {
    let car: RaceActivityAttributes.ContentState.Car
    let favourite: Bool

    var body: some View {
        HStack(spacing: 8) {
            Text("\(car.position)").foregroundStyle(.secondary).frame(width: 18, alignment: .trailing)
            Text(car.code).fontWeight(favourite ? .bold : .medium)
            Spacer()
            if car.inPit { Text("PIT").font(.system(size: 10, weight: .semibold)) } else { Text(car.gap ?? "") }
        }
        .font(.system(size: 13, design: .monospaced))
        .monospacedDigit()
        .foregroundStyle(Palette.of(.dark).t1)
        .overlay(alignment: .leading) {
            if favourite { Rectangle().fill(Tokens.signal).frame(width: 2).offset(x: -8) }
        }
        .contentTransition(.numericText())
    }
}

private struct LockScreenBanner: View {
    let context: ActivityViewContext<RaceActivityAttributes>

    var body: some View {
        let s = context.state
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                if s.final { Text("✓ FINAL · \(s.phase)").font(.system(size: 11, weight: .semibold)).tracking(0.8) }
                else { LiveDot(label: s.phase) }
                Text(context.attributes.raceName).font(.system(size: 11, weight: .semibold)).tracking(0.8)
                    .foregroundStyle(Palette.of(.dark).t2)
                Spacer()
                if let lap = s.lap {
                    Text("L\(lap)\(s.lapsTotal.map { " / \($0)" } ?? "")").font(.system(size: 11, weight: .semibold, design: .monospaced))
                }
            }
            HStack(alignment: .top, spacing: 20) {
                VStack(spacing: 4) { ForEach(s.top, id: \.code) { CarRow(car: $0, favourite: $0.code == s.favourite?.code) } }
                if let f = s.favourite {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("P\(f.position)").font(.system(size: 32, weight: .semibold, design: .monospaced))
                        Text(f.inPit ? "PIT" : "\(f.code) \(f.gap ?? "")").font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(Palette.of(.dark).t2)
                    }
                }
            }
            if let lap = s.lap, let total = s.lapsTotal, total > 0 {
                ProgressView(value: Double(lap), total: Double(total)).tint(Tokens.signal)
            }
        }
        .foregroundStyle(Palette.of(.dark).t1)
    }
}
