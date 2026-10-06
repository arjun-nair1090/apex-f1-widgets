import SwiftUI

// Mirrors shared/design-tokens/tokens.json. Change the JSON first.

enum Theme: String, CaseIterable, Codable { case dark, amoled, light }
enum Accent: String, CaseIterable, Codable { case system, team, red }
enum Density: String, CaseIterable, Codable { case minimal, standard, detailed }

struct Palette {
    let background, surface, elevated, border, t1, t2, t3: Color

    static func of(_ theme: Theme) -> Palette {
        switch theme {
        case .dark: Palette(background: .hex("08090B"), surface: .hex("111318"), elevated: .hex("181B21"),
                            border: .hex("23262E"), t1: .hex("F5F7FA"), t2: .hex("9298A3"), t3: .hex("5C626D"))
        case .amoled: Palette(background: .black, surface: .black, elevated: .hex("0C0D10"),
                              border: .hex("1C1F25"), t1: .hex("F5F7FA"), t2: .hex("9298A3"), t3: .hex("5C626D"))
        case .light: Palette(background: .hex("F3F4F6"), surface: .white, elevated: .hex("F0F1F4"),
                             border: .hex("E2E4E9"), t1: .hex("0B0D11"), t2: .hex("5A606B"), t3: .hex("8C919B"))
        }
    }
}

enum Tokens {
    static let signal = Color.hex("FF5A1F")
    static let signalOnLight = Color.hex("E0440C")
    static let motorsportRed = Color.hex("E10D2E")
    static let sectorOverall = Color.hex("A879FF")
    static let sectorPersonal = Color.hex("2FD27F")
    static let sectorNone = Color.hex("E8C547")

    // 8px grid
    static let xs: CGFloat = 4, s: CGFloat = 8, m: CGFloat = 12, l: CGFloat = 16, xl: CGFloat = 24
    static let railHeight: CGFloat = 2
}

extension Color {
    static func hex(_ hex: String) -> Color {
        let v = UInt64(hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) ?? 0
        return Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
    }
}

// Type scale (tokens.typography.scale). Numbers are always tabular.
extension Font {
    static let apexHero = Font.system(size: 44, weight: .semibold, design: .monospaced)
    static let apexDisplay = Font.system(size: 32, weight: .semibold, design: .monospaced)
    static let apexBig = Font.system(size: 22, weight: .semibold, design: .monospaced)
    static let apexTitle = Font.system(size: 17, weight: .semibold)
    static let apexData = Font.system(size: 13, weight: .medium, design: .monospaced)
    static let apexMeta = Font.system(size: 11, weight: .semibold)
    static let apexMicro = Font.system(size: 9, weight: .semibold)
}

extension Text {
    /// Small uppercase metadata.
    func meta(_ color: Color) -> some View {
        font(.apexMeta).tracking(0.8).textCase(.uppercase).foregroundStyle(color)
    }

    func micro(_ color: Color) -> some View {
        font(.apexMicro).tracking(0.8).textCase(.uppercase).foregroundStyle(color)
    }
}
