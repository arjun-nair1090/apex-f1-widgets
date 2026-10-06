using System.Text.Json;

namespace Apex;

public enum Kind { Race, Next, Countdown, Timing, Driver, Favourite, Wdc, Wcc, Weekend }

/// Per-widget settings, stored in the widget's CustomState by the Widgets Board.
public record WidgetSettings(string? Driver = null, string Density = "standard");

/// Turns a snapshot into (template, data) for one widget at one size. Templates: Widgets/*.json.
public static class Cards
{
    static readonly Dictionary<string, string> Templates = Directory.GetFiles(Path.Combine(AppContext.BaseDirectory, "Widgets"), "*.json")
        .ToDictionary(f => Path.GetFileNameWithoutExtension(f), File.ReadAllText);

    public static string Template(string name) => Templates[name];

    public static (string template, string data) Build(Kind kind, string size, Loaded? loaded, WidgetSettings cfg, DateTimeOffset now)
    {
        if (loaded is null) return ("empty", Json(new { unavailable = true, updated = "—", stale = "", cc = "", race = "", session = "", when = "", countdown = "" }));
        var s = loaded.Snapshot;
        var stale = loaded.StaleSince is { } since && now - since > TimeSpan.FromMinutes(2) ? $"LAST UPDATED {Fmt.Ago(since, now)} AGO" : "";
        var mode = RaceMode.Of(s, now);
        return kind switch
        {
            Kind.Race => mode switch
            {
                Mode.Live => Timing(s, s.Live, size, cfg, now, stale),
                Mode.Results => Timing(s, s.Results, size, cfg, now, stale),
                Mode.Countdown => Countdown(s, RaceMode.NextSession(s, now), now, stale),
                _ => Next(s, now, stale),
            },
            Kind.Next => Next(s, now, stale),
            Kind.Countdown => Countdown(s, s.Race?.Sessions.FirstOrDefault(x => x.Type == "RACE"), now, stale),
            Kind.Timing => Timing(s, mode == Mode.Results ? s.Results : s.Live, size, cfg, now, stale),
            Kind.Driver => Driver(s, stale),
            Kind.Favourite => Favourite(s, mode, now, stale),
            Kind.Wdc or Kind.Wcc => Standings(s, kind == Kind.Wdc, size, cfg, stale),
            _ => Weekend(s, now, stale),
        };
    }

    static string Json(object o) => JsonSerializer.Serialize(o);
    static string Cc(Race? r) => r?.CountryCode ?? "";

    static object[] WeekendRows(Race r, DateTimeOffset now) => r.Sessions.Select(x =>
    {
        var st = RaceMode.State(x, now);
        return (object)new
        {
            day = Fmt.Day(x.StartsAt), name = x.Label, live = st == "live", done = st == "finished",
            glyph = st switch { "finished" => "✓", "live" => "●", "starting_soon" => "◐", _ => "○" },
            time = st switch { "live" => "LIVE", "finished" => "", _ => Fmt.HhMm(x.StartsAt) },
        };
    }).ToArray();

    static (string, string) Next(WidgetSnapshot s, DateTimeOffset now, string stale)
    {
        var n = RaceMode.NextSession(s, now);
        if (n is null) return ("empty", Json(new { unavailable = false, stale, cc = "", race = "SEASON COMPLETE", session = "", when = "", countdown = "" }));
        if (RaceMode.State(n, now) == "live") return Timing(s, s.Live, "medium", new(), now, stale);
        var soon = RaceMode.State(n, now) == "starting_soon";
        return ("next", Json(new
        {
            cc = Cc(s.Race), race = s.Race?.ShortName ?? "", raceShort = s.Race?.ShortName.Replace(" GP", "") ?? "",
            tag = soon ? "◐ SOON" : $"R{s.Race?.Round}", session = n.Label,
            sessionTitle = n.Label.Any(char.IsDigit) ? n.Label : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(n.Label.ToLowerInvariant()),
            when = Fmt.DayTime(n.StartsAt), countdown = Fmt.Countdown(n.StartsAt, now),
            weekend = s.Race is null ? [] : WeekendRows(s.Race, now), circuit = s.Race?.CircuitName ?? "", stale,
        }));
    }

    static (string, string) Countdown(WidgetSnapshot s, Session? target, DateTimeOffset now, string stale)
    {
        if (target is null) return Next(s, now, stale);
        var st = RaceMode.State(target, now);
        if (st is "live" or "finished") return Build(Kind.Race, "medium", new Loaded(s, null), new(), now);  // LIVE at lights out (spec §8)
        var t = target.StartsAt - now;
        return ("countdown", Json(new
        {
            label = Fmt.Short(target.Type), cc = Cc(s.Race), race = s.Race?.ShortName ?? "", when = Fmt.DayTime(target.StartsAt),
            days = t.Days > 0 ? Fmt.Pad(t.Days) : "", hms = $"{t.Hours:00}:{t.Minutes:00}:{t.Seconds:00}",
            circuit = s.Race?.CircuitName ?? "", stale,
        }));
    }

    static (string, string) Timing(WidgetSnapshot s, Timing? t, string size, WidgetSettings cfg, DateTimeOffset now, string stale)
    {
        var next = RaceMode.NextSession(s, now);
        if (t is null)
        {
            var unavailable = RaceMode.Of(s, now) == Mode.Live && s.LiveUnavailable;
            return ("empty", Json(new
            {
                unavailable, updated = Fmt.Ago(s.GeneratedAt, now).ToLowerInvariant(), stale, cc = Cc(s.Race), race = s.Race?.ShortName ?? "",
                session = next?.Label ?? "", when = next is null ? "" : Fmt.DayTime(next.StartsAt),
                countdown = next is null ? "" : Fmt.Countdown(next.StartsAt, now),
            }));
        }
        var fav = s.Driver?.Code;
        var label = t.Phase ?? Fmt.Short(t.SessionType);
        int n = size == "large" ? cfg.Density switch { "minimal" => 6, "detailed" => 12, _ => 10 } : cfg.Density == "minimal" ? 3 : 6;
        var rows = t.Rows.Take(n).ToList();
        if (fav is not null && n > 2 && rows.All(r => r.Code != fav) && t.Rows.FirstOrDefault(r => r.Code == fav) is { } f) rows = [.. rows.Take(n - 1), f];
        string Value(TimingRow r) => r.InPit ? "PIT" : r.Position == 1 ? (!t.IsRace || t.Final ? r.Time ?? "" : "") : r.Gap ?? "";
        // Sector glyphs carry the meaning without color (spec §28); Adaptive Cards can't color per character anyway.
        string Sectors(TimingRow r) => cfg.Density == "minimal" ? "" : string.Concat((r.Sectors ?? []).Select(x => x switch { "purple" => "◆", "green" => "▲", "yellow" => "–", _ => "·" }));
        // Adaptive Card text must be strings: numbers would render as empty TextBlocks.
        var view = rows.Select(r => new { pos = r.Position.ToString(), lead = r.Position == 1, code = r.Code, value = Value(r), fav = r.Code == fav, sectors = Sectors(r),
            interval = cfg.Density == "detailed" ? r.Interval ?? "" : "" }).ToList();
        var p1 = t.Rows.FirstOrDefault();
        return ("timing", Json(new
        {
            tag = t.Final ? $"✓ FINAL · {label}" : size == "small" ? "● LIVE" : $"● LIVE · {label}", live = !t.Final,
            lap = t.Lap is null ? "" : size == "small" || t.LapsTotal is null ? $"L{t.Lap}" : $"L{t.Lap} / {t.LapsTotal}",
            cc = Cc(s.Race), race = s.Race?.ShortName ?? "",
            p1 = new { pos = p1?.Position ?? 1, code = p1?.Code ?? "", value = p1 is null || t.IsRace ? "" : p1.Time ?? "" },
            rows = view, rowsLeft = view.Take(3), rowsRight = view.Skip(3), stale,
        }));
    }

    static (string, string) Driver(WidgetSnapshot s, string stale)
    {
        var d = s.Driver;
        if (d is null) return ("driver", Json(new { chosen = false, stale }));
        return ("driver", Json(new
        {
            chosen = true, name = $"{d.FirstName} {d.LastName}".ToUpperInvariant(), code = d.Code, team = d.TeamName ?? "", cc = d.CountryCode ?? "",
            pos = d.Position is { } p ? $"P{p}" : "—", points = Fmt.Points(d.Points), wins = d.Wins.ToString(), podiums = d.Podiums.ToString(), poles = d.Poles.ToString(),
            showStats = true, last5 = string.Join(" · ", d.Last5.Select(x => x is { } v ? $"P{v}" : "DNF")), last5Count = d.Last5.Count, stale,
        }));
    }

    static (string, string) Favourite(WidgetSnapshot s, Mode mode, DateTimeOffset now, string stale)
    {
        var d = s.Driver;
        if (d is null) return ("favourite", Json(new { chosen = false, stale }));
        var row = mode == Mode.Live ? s.Live?.Rows.FirstOrDefault(r => r.Code == d.Code) : null;
        var race = d.Weekend.FirstOrDefault(w => w.SessionType == "RACE" && w.Position is not null);
        var quali = d.Weekend.FirstOrDefault(w => w.SessionType == "QUALIFYING" && w.Position is not null);
        // Whatever matters now (spec §14).
        var (label, live, big, top, sub) = row is not null
            ? (s.Live!.Phase ?? Fmt.Short(s.Live.SessionType), true, $"P{row.Position}", s.Live.Lap is { } l ? $"L{l}" : "",
               row.InPit ? "PIT" : row.Position == 1 ? (s.Live.IsRace ? "LEADER" : row.Time ?? "") : row.Gap ?? "")
            : race is not null ? ("✓ RACE", false, $"P{race.Position}", "", race.Gap ?? (race.Position == 1 ? "WINNER" : ""))
            : quali is not null ? ("GRID", false, $"QUALI P{quali.Position}", "", "")
            : ("CHAMPIONSHIP", false, d.Position is { } p ? $"P{p}" : "—", "", $"{Fmt.Points(d.Points)} PTS");
        return ("favourite", Json(new { chosen = true, label = live ? $"● LIVE · {label}" : label, live, big, top, sub, code = d.Code,
            name = d.LastName.ToUpperInvariant(), stale }));
    }

    static (string, string) Standings(WidgetSnapshot s, bool drivers, string size, WidgetSettings cfg, string stale)
    {
        var n = size switch { "small" => 3, "medium" => cfg.Density == "minimal" ? 3 : 5, _ => cfg.Density == "minimal" ? 6 : 10 };
        var leader = s.Drivers.FirstOrDefault()?.Points ?? 0;
        var all = drivers
            ? s.Drivers.Select(d => (pos: d.Position, name: d.Code, points: d.Points, fav: d.Code == s.Driver?.Code)).ToList()
            : s.Constructors.Select(c => (pos: c.Position, name: c.ShortName, points: c.Points, fav: c.TeamId == s.Driver?.TeamId)).ToList();
        var shown = all.Take(n).ToList();
        if (!shown.Any(x => x.fav) && n > 2)
        {
            var fav = all.FirstOrDefault(x => x.fav);
            if (fav == default && drivers && s.Driver?.Position is { } p) fav = (p, s.Driver.Code, s.Driver.Points, true);
            if (fav != default) shown = [.. shown.Take(n - 1), fav];
        }
        return ("standings", Json(new
        {
            title = drivers ? "WDC" : "WCC", after = s.Race is null ? "" : $"AFTER R{Math.Max(1, s.Race.Round - 1)}", stale,
            rows = shown.Select(x => new { pos = Fmt.Pad(x.pos), x.name, x.fav, points = Fmt.Points(x.points),
                gap = size == "large" && cfg.Density == "detailed" && drivers && x.pos > 1 ? $"−{Fmt.Points(leader - x.points)}" : "" }),
        }));
    }

    static (string, string) Weekend(WidgetSnapshot s, DateTimeOffset now, string stale)
    {
        if (s.Race is not { } r) return Next(s, now, stale);
        var n = RaceMode.NextSession(s, now);
        var live = n is not null && RaceMode.State(n, now) == "live";
        return ("weekend", Json(new
        {
            cc = Cc(r), race = r.ShortName, raceShort = r.ShortName.Replace(" GP", ""), tag = $"R{r.Round}", weekend = WeekendRows(r, now),
            glyphs = string.Join(" ", r.Sessions.Select(x => RaceMode.State(x, now) switch { "finished" => "✓", "live" => "●", _ => "○" })),
            nextLabel = n is null ? "" : live ? $"● {n.Label}" : n.Label, nextLive = live,
            nextWhen = n is null ? "" : live ? "LIVE NOW" : Fmt.DayTime(n.StartsAt),
            nextCountdown = n is null || live ? "" : Fmt.Countdown(n.StartsAt, now), circuit = r.CircuitName, stale,
        }));
    }
}
