/* APEX widget renderer, shared by index.html (preview) and desktop.html (desktop widgets).
   APEX.render(id, size, view, now, opts) → HTML. `view` is a WidgetSnapshot (+ stale/loading flags);
   opts = { platform, theme, accent, density, teamColors, snap, fetchedAt }. */
"use strict";
const APEX = (() => {
  const WIDGETS = [
    ["race", "APEX", "Race Mode"], ["next", "Next session", ""], ["countdown", "Countdown", ""], ["timing", "Live timing", ""],
    ["driver", "Driver", ""], ["fav", "Favourite driver", "smart"], ["wdc", "Drivers' title", "WDC"],
    ["wcc", "Constructors' title", "WCC"], ["weekend", "Race weekend", ""], ["track", "Circuit", "3D"],
  ];
  let O = {};  // options for the render in progress

  // ---------- formatting (tokens.json "format") ----------
  const pad = n => String(n).padStart(2, "0");
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const flag = cc => String.fromCodePoint(...[...cc.toUpperCase()].map(c => 0x1f1a5 + c.charCodeAt(0)));
  const noFlagEmoji = /Windows/.test(navigator.userAgent);  // Windows fonts have no flag emoji
  const country = cc => !cc ? "" : O.platform === "windows" || noFlagEmoji ? `<span class="cc">${esc(cc)}</span>` : `<span class="flag" aria-hidden="true">${flag(cc)}</span>`;
  const weekday = d => d.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase();
  const hhmm = iso => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  const dayTime = iso => `${weekday(new Date(iso))} · ${hhmm(iso)}`;
  const dayOnly = iso => weekday(new Date(iso));
  const parts = (iso, now) => { let s = Math.max(0, Math.floor((Date.parse(iso) - now) / 1000));
    return { d: Math.floor(s / 86400), h: Math.floor(s % 86400 / 3600), m: Math.floor(s % 3600 / 60), s: s % 60 }; };
  const ago = ms => { const s = Math.round(ms / 1000); return s < 60 ? `${s}S` : s < 3600 ? `${Math.round(s / 60)}M` : `${Math.round(s / 3600)}H`; };
  const pts = p => Number.isInteger(p) ? p : p.toFixed(1);
  const shortCountry = r => r ? r.short_name.replace(/ GP$/, "") : "";
  const sessionLabel = t => ({ RACE: "RACE", SPRINT: "SPRINT", QUALIFYING: "QUALI", SPRINT_QUALIFYING: "SPRINT QUALI" }[t] || t);
  // Colours go into style attributes: only RRGGBB (the backend filters too; this is the second gate).
  const hexColor = c => /^[0-9A-Fa-f]{6}$/.test(c ?? "") ? `#${c}` : null;
  /** Driver silhouette URL. Bump `v` when its style changes: browsers cache it for a day. */
  const silhouette = (id, size) => `/api/drivers/${encodeURIComponent(id)}/silhouette.png?size=${size}&v=6`;

  // ---------- Race Mode (mirror of backend/apex/racemode.py) ----------
  function raceMode(sessions, now) {
    const o = [...sessions].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));
    const live = o.find(s => Date.parse(s.starts_at) <= now && now < Date.parse(s.ends_at));
    if (live) return ["live", live];
    const ended = o.filter(s => Date.parse(s.ends_at) <= now).pop();
    if (ended && now - Date.parse(ended.ends_at) < 90 * 60e3) return ["results", ended];
    const up = o.find(s => Date.parse(s.starts_at) > now);
    if (!up) return ["next", null];
    return [Date.parse(up.starts_at) - now <= 3 * 3600e3 ? "countdown" : "next", up];
  }
  function stateOf(s, now) {
    const a = Date.parse(s.starts_at), b = Date.parse(s.ends_at);
    return now >= b ? "finished" : now >= a ? "live" : now >= a - 15 * 60e3 ? "starting_soon" : "upcoming";
  }

  // ---------- primitives ----------
  const tab = (text, red, live, still) => `<span class="tab${red ? " red" : ""}">${live ? `<i class="dot${still ? " still" : ""}" aria-hidden="true"></i>` : ""}${esc(text)}</span>`;
  const liveTab = label => tab(label ? `Live · ${label}` : "Live", true, true);
  const raceRight = v => `${country(v.race?.country_code)}<span class="lbl trunc" style="color:var(--wt1)">${esc(v.race?.short_name ?? "")}</span>`;
  const head = (left, right = "") => `<div class="row">${left}<span class="sp"></span>${right}</div>`;
  const rail = (frac, on) => frac == null ? "" : `<div class="rail${on ? " on" : ""}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(frac * 100)}"><i style="width:${(Math.max(0, Math.min(1, frac)) * 100).toFixed(1)}%"></i></div>`;
  const stripe = c => `<i class="stripe" style="--c:${hexColor(c) ?? "var(--wt3)"}" aria-hidden="true"></i>`;
  const secG = s => !s ? "" : `<span class="sec" aria-label="sectors">${s.map(x => x === "purple" ? `<span class="pu">◆</span>` : x === "green" ? `<span class="gr">▲</span>` : x === "yellow" ? `<span class="ye">–</span>` : `<span class="na">·</span>`).join("")}</span>`;
  const stale = v => v.stale > 60e3 ? `<div class="stale">Last updated ${ago(v.stale)} ago</div>` : "";

  /** F1.com-style countdown: DAYS HRS MINS SECS in boxes. `max` caps how many boxes fit. */
  function boxes(iso, now, size = "", max = 4, soon = false) {
    const p = parts(iso, now);
    let units = [[p.d, "DAYS"], [p.h, "HRS"], [p.m, "MINS"], [p.s, "SECS"]];
    if (!p.d) units = units.slice(1);
    units = units.slice(0, max);
    return `<div class="boxes ${size}${soon ? " soon" : ""}" role="timer" aria-label="${p.d} days ${p.h} hours ${p.m} minutes">${units.map(([n, l]) => `<div class="box"><b>${pad(n)}</b><span>${l}</span></div>`).join("")}</div>`;
  }
  function countdownRail(v, ns, now) {
    if (!ns || !v.race) return null;
    const prev = v.race.sessions.filter(s => Date.parse(s.ends_at) <= Date.parse(ns.starts_at) && s.id !== ns.id).pop();
    const from = prev ? Date.parse(prev.ends_at) : Date.parse(ns.starts_at) - 7 * 864e5;
    return (now - from) / (Date.parse(ns.starts_at) - from);
  }
  function progressOf(v, t, now) {
    const s = v.race?.sessions.find(x => x.id === t.session_id); if (!s) return null;
    return (now - Date.parse(s.starts_at)) / (Date.parse(s.ends_at) - Date.parse(s.starts_at));
  }

  /** Big glowing race number + the driver's glowing team-colour silhouette, with a light sweep across it. */
  function driverArt(d, z) {
    const team = hexColor(d.team_color) ?? "var(--acc)";
    const num = d.race_number ?? d.number ?? "";
    const size = z === "l" ? 864 : z === "m" ? 432 : 206;
    const src = silhouette(d.id, size);
    return `<div class="dc" style="--team:${team}" aria-hidden="true"><span class="bignum">${esc(num)}</span>
      <div class="sil" style="--sil:url('${src}')"><img src="${src}" alt="" onerror="this.parentNode.remove()"><i class="shine"></i></div></div>`;
  }
  const pickDriver = () => `${head(tab("Driver"))}<div class="grow"></div><div class="hd">Choose a driver</div><div class="lbl" style="margin-top:6px">Pick one in settings</div>`;

  // ---------- timing rows ----------
  function rowsFor(t, n, fav, showSec, showInt) {
    let rows = t.rows.slice(0, n);
    const f = t.rows.find(r => r.code === fav);
    const more = f && !rows.includes(f) && n > 2;
    if (more) rows = rows.slice(0, n - 1);
    const quali = !["RACE", "SPRINT"].includes(t.session_type);
    const line = (r, extra = "") => {
      const val = r.in_pit ? `<span class="pit">PIT</span>` : r.position === 1 ? (quali || t.final ? esc(r.time ?? "") : "LEADER") : esc(r.gap ?? "");
      return `<div class="tr${r.code === fav ? " fav" : ""}${extra}" data-code="${esc(r.code)}"><span class="p">${r.position}</span>${stripe(r.team_color)}<span class="code">${esc(r.code)}</span><span class="v${r.position === 1 ? " lead" : ""}">${showSec ? secG(r.sectors) : ""}${val}${showInt && r.interval ? ` <span class="t3">${esc(r.interval)}</span>` : ""}</span></div>`;
    };
    return rows.map(r => line(r)).join("") + (more ? line(f, " more") : "");
  }

  // ---------- widgets ----------
  const R = {};

  R.next = (v, z, now) => {
    const ns = v.next_session;
    if (!ns) return `${head(tab("Season"))}<div class="grow"></div><div class="hd">Season complete</div><div class="lbl" style="margin-top:6px">See you next year</div>`;
    if (stateOf(ns, now) === "live") return R.timing(v, z, now);
    const soon = stateOf(ns, now) === "starting_soon";
    const label = ns.label, rl = rail(countdownRail(v, ns, now));
    const t = soon ? tab("Starting soon", true) : tab("Next");
    if (z === "s") return `${head(t, country(v.race?.country_code))}<div class="grow"></div>
      <div class="lbl" style="color:var(--wt1)">${esc(shortCountry(v.race))}</div>
      <div class="hd" style="font-size:${label.length > 8 ? 17 : 21}px;margin-top:4px">${esc(label)}</div>
      <div class="lbl dim" style="margin:4px 0 8px">${dayTime(ns.starts_at)}</div>${boxes(ns.starts_at, now, "small", 3, soon)}${rl}${stale(v)}`;
    const bottom = `<div class="row" style="align-items:flex-end;gap:12px"><div class="col" style="gap:5px;flex:1">
        <div class="hd">${esc(label)}</div><div class="lbl dim">${dayTime(ns.starts_at)}</div></div>${boxes(ns.starts_at, now, "", 3, soon)}</div>`;
    if (z === "m") return `${head(t, raceRight(v))}${trackCanvas(v, "flow")}${bottom}${rl}${stale(v)}`;
    return `${head(t, raceRight(v))}<div style="margin-top:14px">${weekendList(v, now)}</div>
      ${trackCanvas(v, "flow")}<div class="lbl dim" style="margin-bottom:8px">${esc(v.race?.circuit_name ?? "")}</div>
      <div class="hd" style="font-size:26px">${esc(label)}</div><div class="lbl dim" style="margin:5px 0 10px">${dayTime(ns.starts_at)}</div>
      ${boxes(ns.starts_at, now, "big", 4, soon)}${rl}${stale(v)}`;
  };

  R.countdown = (v, z, now, target) => {
    const sess = target || v.race?.sessions.find(s => s.type === "RACE");
    if (!sess) return R.next(v, z, now);
    if (stateOf(sess, now) === "live") return R.timing(v, z, now);
    if (stateOf(sess, now) === "finished") return R.next(v, z, now);
    const name = sessionLabel(sess.type), soon = stateOf(sess, now) === "starting_soon";
    const rl = rail(countdownRail(v, sess, now));
    if (z === "s") return `${head(tab(`${name} in`, soon), country(v.race?.country_code))}<div class="grow"></div>
      ${boxes(sess.starts_at, now, "small", 3, soon)}<div class="lbl dim" style="margin-top:8px">${dayTime(sess.starts_at)}</div>${rl}${stale(v)}`;
    if (z === "m") return `${head(tab(name === "RACE" ? "Lights out in" : `${name} in`, true), raceRight(v))}<div class="grow"></div>
      ${boxes(sess.starts_at, now, "big", 4, soon)}<div class="row" style="margin-top:8px"><span class="lbl dim">${dayTime(sess.starts_at)}</span><span class="sp"></span><span class="lbl dim trunc">${esc(v.race?.circuit_name ?? "")}</span></div>${rl}${stale(v)}`;
    return `${head(tab(name === "RACE" ? "Lights out in" : `${name} in`, true), `<span class="lbl dim">Round ${v.race?.round ?? ""}</span>`)}
      <div style="margin-top:16px">${country(v.race?.country_code)}</div>
      <div class="num lg" style="margin-top:8px">${esc(v.race?.short_name ?? "")}</div>
      <div class="lbl dim" style="margin:6px 0 16px">${esc(v.race?.circuit_name ?? "")}</div>
      ${boxes(sess.starts_at, now, "big", 4, soon)}<div class="lbl" style="margin-top:10px">${dayTime(sess.starts_at)}</div>
      ${trackCanvas(v, "flow")}<div style="margin-bottom:6px">${weekendList(v, now, 3)}</div>${rl}${stale(v)}`;
  };

  R.timing = (v, z, now, results) => {
    const t = results ? v.results : v.live;
    if (!t) return emptyLive(v, z, now);
    const quali = !["RACE", "SPRINT"].includes(t.session_type);
    const label = t.phase || sessionLabel(t.session_type);
    const t1 = t.final ? tab(`Final · ${label}`) : liveTab(z === "s" ? "" : label);
    const lap = t.lap ? `<span class="lbl" style="color:var(--wt1)">Lap ${t.lap}${t.laps_total && z !== "s" ? ` / ${t.laps_total}` : ""}</span>` : "";
    const progress = t.final ? null : t.lap && t.laps_total ? t.lap / t.laps_total : progressOf(v, t, now);
    const fav = O.snap?.driver?.code, d = O.density;
    if (z === "s") { const p1 = t.rows[0];
      return `${head(t1, lap)}<div class="grow"></div><div class="row" style="align-items:flex-end;gap:8px"><span class="num lg">P1</span>${stripe(p1?.team_color)}</div>
        <div class="hd" style="margin-top:4px">${esc(p1?.code ?? "")}</div>
        <div class="lbl dim" style="margin-top:4px">${quali && !t.final ? esc(p1?.time ?? "") : esc(t.rows[1] ? `${t.rows[1].code} ${t.rows[1].gap ?? ""}` : "")}</div>${rail(progress, true)}${stale(v)}`; }
    if (z === "m") { const n = d === "minimal" ? 3 : 6;
      return `${head(t1, lap)}<div class="grow"></div><div class="tower ${n > 3 ? "cols2" : ""}" style="${n > 3 ? "grid-auto-flow:column;grid-template-rows:repeat(3,18px)" : ""}">${rowsFor(t, n, fav, false, false)}</div>${rail(progress, !t.final)}${stale(v)}`; }
    const n = d === "minimal" ? 6 : d === "detailed" ? 12 : 10;
    return `${head(t1, lap)}<div class="row" style="margin-top:8px">${raceRight(v)}</div><div class="grow"></div>
      <div class="tower">${rowsFor(t, n, fav, d !== "minimal", d === "detailed")}</div>${rail(progress, !t.final)}${stale(v)}`;
  };

  function emptyLive(v, z, now) {
    const ns = v.next_session;
    if (v.live_unavailable) return `${head(tab("Live", true, true, true))}<div class="grow"></div>
      <div class="hd" style="font-size:${z === "s" ? 16 : 20}px">Live data unavailable</div>
      ${z === "s" ? "" : `<div class="lbl" style="margin-top:6px">Using cached data · updated ${ago(Math.max(42e3, now - (O.fetchedAt || now))).toLowerCase()} ago</div>`}
      <div class="row" style="margin-top:10px"><button class="retry" onclick="APEX.retry()">Retry</button></div>`;
    if (!ns) return `${head(tab("No live session"))}`;
    if (z === "s") return `${head(tab("Off track"))}<div class="grow"></div><div class="lbl">Next</div>
      <div class="hd" style="font-size:18px;margin:4px 0 8px">${esc(ns.label)}</div>${boxes(ns.starts_at, now, "small", 3)}${stale(v)}`;
    return `${head(tab("No live session"), raceRight(v))}<div class="grow"></div><div class="lbl dim">Next session</div>
      <div class="row" style="align-items:flex-end;gap:12px;margin-top:6px"><div class="col" style="gap:5px;flex:1"><div class="hd">${esc(ns.label)}</div>
      <div class="lbl dim">${dayTime(ns.starts_at)}</div></div>${boxes(ns.starts_at, now, "", 3)}</div>${stale(v)}`;
  }

  R.driver = (v, z) => {
    const d = v.driver; if (!d) return pickDriver();
    const pos = d.position ? `P${d.position}` : "—";
    const name = `<div class="dn-first">${esc(d.first_name)}</div><div class="dn-last trunc" style="max-width:${z === "s" ? 120 : 210}px">${esc(d.last_name)}</div>`;
    const top = head(tab(`${pos} · ${pts(d.points)} pts`, true));
    if (z === "s") return `${driverArt(d, z)}<div class="dc-text col" style="height:100%">${top}<div class="grow"></div>${name}
      <div class="lbl trunc" style="margin-top:5px;max-width:110px">${esc(d.team_name ?? "")}</div></div>${stale(v)}`;
    const stats = O.density === "minimal" ? "" : `<div class="stats" style="margin-top:10px"><div><span class="lbl">Wins</span><b>${d.wins}</b></div><div><span class="lbl">Podiums</span><b>${d.podiums}</b></div><div><span class="lbl">Poles</span><b>${d.poles}</b></div></div>`;
    const team = `<div class="row" style="margin-top:6px;gap:6px"><i class="teamline" style="--team:${hexColor(d.team_color) ?? "var(--acc)"}"></i><span class="lbl">${esc(d.team_name ?? "")}</span></div>`;
    if (z === "m") return `${driverArt(d, z)}<div class="dc-text col" style="height:100%">${top}<div class="grow"></div>${name}${team}${stats}</div>${stale(v)}`;
    const l5 = d.last5.length ? `<div class="lbl" style="margin:14px 0 6px">Last ${d.last5.length} races</div><div class="last5">${d.last5.map(p => `<span class="${p && p <= 3 ? "pod" : ""}">${p ? "P" + p : "DNF"}</span>`).join("")}</div>` : "";
    return `${driverArt(d, z)}<div class="dc-text col" style="height:100%">${top}<div class="grow"></div>${name}${team}${stats}${O.density === "minimal" ? "" : l5}</div>${stale(v)}`;
  };

  R.fav = (v, z, now) => {
    const d = v.driver; if (!d) return pickDriver();
    const live = v.mode === "live" && v.live?.rows.find(r => r.code === d.code);
    const race = d.weekend?.find(w => w.session_type === "RACE" && w.position);
    const quali = d.weekend?.find(w => w.session_type === "QUALIFYING" && w.position);
    let t, big, sub;
    if (live) { t = liveTab(z === "s" ? "" : (v.live.phase || sessionLabel(v.live.session_type))); big = `P${live.position}`;
      sub = live.in_pit ? "IN THE PIT LANE" : live.position === 1 ? (v.live.lap ? `LEADING · LAP ${v.live.lap}` : live.time) : `${live.gap ?? ""}${v.live.lap ? ` · LAP ${v.live.lap}` : ""}`; }
    else if (race) { t = tab("Race result"); big = `P${race.position}`; sub = race.position === 1 ? "WINNER" : race.gap ?? ""; }
    else if (quali) { const rs = v.race?.sessions.find(s => s.type === "RACE"); t = tab("Grid"); big = `P${quali.position}`;
      sub = rs ? `RACE ${dayTime(rs.starts_at)}` : "QUALIFYING"; }
    else { t = tab("Championship"); big = d.position ? `P${d.position}` : "—"; sub = `${pts(d.points)} PTS`; }
    const nameMax = z === "s" ? 120 : 200;
    const progress = live ? rail(v.live.lap && v.live.laps_total ? v.live.lap / v.live.laps_total : progressOf(v, v.live, now), true) : "";
    return `${driverArt(d, z)}<div class="dc-text col" style="height:100%">${head(t)}<div class="grow"></div>
      <div class="num ${z === "s" ? "lg" : "xl"}">${esc(big)}</div>
      <div class="dn-last trunc" style="max-width:${nameMax}px;font-size:${z === "s" ? 18 : 22}px;margin-top:4px">${esc(z === "s" ? d.code : d.last_name)}</div>
      <div class="lbl trunc" style="margin-top:5px;max-width:${nameMax}px;${live ? "color:var(--wt1)" : ""}">${esc(sub)}</div>
      ${z === "l" ? `<div class="stats" style="margin-top:14px"><div><span class="lbl">Season</span><b>P${d.position ?? "—"}</b></div><div><span class="lbl">Points</span><b>${pts(d.points)}</b></div><div><span class="lbl">Wins</span><b>${d.wins}</b></div></div>` : ""}
      </div>${progress}${stale(v)}`;
  };

  function standings(rows, z, kind, v) {
    const d = O.density, n = z === "s" ? 4 : z === "m" ? (d === "minimal" ? 3 : 5) : (d === "minimal" ? 6 : 12);
    const favKey = kind === "wdc" ? v.driver?.code : v.driver?.team_id;
    const key = r => kind === "wdc" ? r.code : r.team_id;
    let shown = rows.slice(0, n), extra = "";
    if (favKey && !shown.some(r => key(r) === favKey) && n > 2) {
      shown = shown.slice(0, n - 1);
      const fr = rows.find(r => key(r) === favKey) || (kind === "wdc" && v.driver?.position ? { position: v.driver.position, code: v.driver.code, team_color: v.driver.team_color, points: v.driver.points } : null);
      if (fr) extra = line(fr, " more");
    }
    const leader = rows[0]?.points ?? 0;
    function line(r, cls = "") {
      const name = kind === "wdc" ? `<span class="code">${esc(r.code)}</span>` : `<span class="team trunc">${esc(r.short_name)}</span>`;
      const gap = z === "l" && d === "detailed" && r.position > 1 ? `<span class="t3" style="margin-right:10px">−${pts(leader - r.points)}</span>` : "";
      return `<div class="tr${key(r) === favKey ? " fav" : ""}${cls}"><span class="p">${r.position}</span>${stripe(r.team_color ?? r.color)}${name}<span class="v lead">${gap}${pts(r.points)}</span></div>`;
    }
    const round = v.race ? `After R${Math.max(1, (v.race.round ?? 1) - 1)}` : "";
    return `${head(tab(kind === "wdc" ? (z === "s" ? "Drivers" : "Drivers' championship") : (z === "s" ? "Teams" : "Constructors")), z === "s" ? "" : `<span class="lbl dim">${round}</span>`)}
      <div class="grow"></div><div class="tower">${shown.map(r => line(r)).join("")}${extra}</div>${stale(v)}`;
  }
  R.wdc = (v, z) => standings(v.drivers, z, "wdc", v);
  R.wcc = (v, z) => standings(v.constructors, z, "wcc", v);

  function weekendList(v, now, limit) {
    let ss = v.race?.sessions ?? [];
    if (limit) { const i = Math.max(0, ss.findIndex(s => Date.parse(s.ends_at) > now)); ss = ss.slice(Math.min(i, Math.max(0, ss.length - limit)), Math.min(i, Math.max(0, ss.length - limit)) + limit); }
    return `<div class="wk">${ss.map(s => { const st = stateOf(s, now);
      const g = st === "finished" ? "✓" : st === "live" ? "●" : st === "starting_soon" ? "◐" : "○";
      const cls = st === "finished" ? "fin" : st === "live" ? "now" : "";
      const right = st === "live" ? "LIVE" : st === "finished" ? "" : hhmm(s.starts_at);
      return `<span class="d ${cls}">${dayOnly(s.starts_at)}</span><span class="n ${cls}">${esc(s.label)}</span><span class="g ${cls}" aria-label="${st.replace("_", " ")}">${g}</span><span class="tm ${cls}">${right}</span>`; }).join("")}</div>`;
  }
  R.weekend = (v, z, now) => {
    if (!v.race) return head(tab("No upcoming weekend"));
    const ns = v.next_session, nsLive = ns && stateOf(ns, now) === "live";
    if (z === "s") return `${head(tab(`Round ${v.race.round}`), country(v.race.country_code))}
      <div class="hd" style="font-size:19px;margin-top:10px">${esc(shortCountry(v.race))}</div>
      <div class="row" style="margin-top:8px;gap:5px;font-size:13px" aria-label="weekend progress">${v.race.sessions.map(s => { const x = stateOf(s, now); return `<span style="color:var(${x === "live" ? "--acc" : x === "finished" ? "--wt3" : "--wt1"})">${x === "finished" ? "✓" : x === "live" ? "●" : "○"}</span>`; }).join("")}</div>
      <div class="grow"></div>${ns ? `<div class="lbl" style="color:var(${nsLive ? "--acc" : "--wt1"})">${nsLive ? "● " : ""}${esc(ns.label)}</div><div class="lbl dim" style="margin-top:4px">${nsLive ? "Live now" : dayTime(ns.starts_at)}</div>` : ""}${stale(v)}`;
    const top = head(tab(`Round ${v.race.round}`), raceRight(v));
    if (z === "m") return `${top}<div class="grow"></div>${weekendList(v, now)}${stale(v)}`;
    const foot = ns && !nsLive ? `<div class="grow"></div><div class="lbl">Next · ${esc(ns.label)}</div><div style="margin-top:6px">${boxes(ns.starts_at, now, "big", 4)}</div>${rail(countdownRail(v, ns, now))}` : "";
    return `${top}<div class="num md" style="margin-top:14px">${esc(v.race.name)}</div><div class="lbl dim" style="margin:4px 0 14px">${esc(v.race.circuit_name)}</div>${weekendList(v, now)}${foot}${stale(v)}`;
  };

  R.race = (v, z, now) => v.mode === "live" ? R.timing(v, z, now) : v.mode === "results" ? R.timing(v, z, now, true)
    : v.mode === "countdown" ? R.countdown(v, z, now, v.next_session) : R.next(v, z, now);

  R.track = (v, z, now) => {
    const r = v.race;
    if (!r) return head(tab("Circuit"));
    const d = trackData(r.season, r.round);
    const rs = r.sessions.find(s => s.type === "RACE");
    const facts = [r.laps_total ? `${r.laps_total} laps` : "", d?.elevation_m != null ? `${Math.round(d.elevation_m)} m elevation` : ""].filter(Boolean).join(" · ");
    const none = d === null ? `<div class="lbl dim" style="margin:auto 0">New circuit: the map arrives after its first race</div>` : "";
    if (z === "s") return `${head(tab(`Round ${r.round}`), country(r.country_code))}${none || trackCanvas(v, "flow")}
      <div class="lbl trunc" style="color:var(--wt1)">${esc(shortCountry(r))}</div>${stale(v)}`;
    if (z === "m") return `<div class="row" style="flex:1;min-height:0;gap:10px;align-items:stretch">
      <div class="col" style="width:128px;flex:none">${tab(`Round ${r.round}`)}<div class="grow"></div>
        <div class="hd" style="font-size:20px">${esc(shortCountry(r))}</div>
        <div class="lbl dim" style="margin-top:4px;line-height:1.3">${esc(r.circuit_name)}</div>
        <div class="lbl" style="margin-top:6px">${facts}</div></div>
      ${none || trackCanvas(v, "fill")}</div>${stale(v)}`;
    return `${head(tab(`Round ${r.round}`), raceRight(v))}<div class="num md" style="margin-top:12px">${esc(r.circuit_name)}</div>
      <div class="lbl" style="margin-top:6px">${facts}</div>${none || trackCanvas(v, "flow")}
      ${rs && stateOf(rs, now) === "upcoming" ? `<div class="lbl" style="margin-bottom:6px">Lights out in</div>${boxes(rs.starts_at, now, "big", 4)}` : ""}${stale(v)}`;
  };

  // ---------- 3D track: real x/y/z from a lap at this circuit (GET /api/races/{round}/track) ----------
  const tracks = {};  // "season-round" → layout | null (no map) | "loading"
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function trackData(season, round) {
    const key = `${season}-${round}`;
    if (!(key in tracks)) {
      tracks[key] = "loading";
      let saved = null;
      try { saved = JSON.parse(localStorage.getItem(`apex.track.${key}`)); } catch {}
      if (saved?.points) tracks[key] = saved;
      else fetch(`/api/races/${round}/track`)
        .then(r => r.status === 404 ? null : r.ok ? r.json() : Promise.reject(r.status))
        .then(d => { tracks[key] = d?.points ? d : null; if (d?.points) try { localStorage.setItem(`apex.track.${key}`, JSON.stringify(d)); } catch {} })
        .catch(() => setTimeout(() => delete tracks[key], 60e3));  // offline / busy: try again in a minute
    }
    return tracks[key] === "loading" ? undefined : tracks[key];
  }
  const trackCanvas = (v, fit) => v.race ? `<canvas class="track3d ${fit}" data-season="${v.race.season}" data-round="${v.race.round}" role="img" aria-label="${esc(v.race.circuit_name)} track map"></canvas>` : "";

  /** Paint every track canvas under `root`: tilted camera, slow turn, elevation drawn as height (exaggerated ×4). */
  function paint(root = document, t = performance.now()) {
    for (const cv of root.querySelectorAll("canvas.track3d")) {
      const d = trackData(cv.dataset.season, cv.dataset.round);
      const w = cv.clientWidth, h = cv.clientHeight;
      if (!d || w < 24 || h < 24) continue;
      const dpr = devicePixelRatio || 1;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      const g = cv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const css = getComputedStyle(cv), ink = css.color, accent = css.getPropertyValue("--acc").trim() || "#E10600";
      const yaw = 0.6 + (reduceMotion ? 0 : t / 48000 * 2 * Math.PI);      // one turn per 48 s
      const tilt = 1.0, ct = Math.cos(tilt), st = Math.sin(tilt), cy = Math.cos(yaw), sy = Math.sin(yaw);
      const zs = 4 / Math.max(200, d.span_m / 2);                             // metres → map units, ×4
      const s = Math.min(w / 2.25, h / (2.1 * ct + 0.35));
      const ox = w / 2, oy = h / 2 + h * 0.04;
      const P = (x, y, z) => { const xr = x * cy - y * sy, yr = x * sy + y * cy; return [ox + s * xr, oy - s * (yr * ct + z * zs * st)]; };
      const pts = d.points, n = pts.length;
      const path = z0 => { g.beginPath(); pts.forEach(([x, y, z], i) => { const [px, py] = P(x, y, z0 ?? z); i ? g.lineTo(px, py) : g.moveTo(px, py); }); g.closePath(); };
      g.lineJoin = g.lineCap = "round";
      path(0); g.strokeStyle = "rgba(0,0,0,.45)"; g.lineWidth = 6; g.stroke();          // ground shadow
      g.strokeStyle = "rgba(127,127,140,.18)"; g.lineWidth = 1;                         // elevation "curtain"
      g.beginPath(); for (let i = 0; i < n; i += 3) { const [x, y, z] = pts[i]; const a = P(x, y, 0), b = P(x, y, z); g.moveTo(...a); g.lineTo(...b); } g.stroke();
      path(); g.globalAlpha = .22; g.strokeStyle = ink; g.lineWidth = 6; g.stroke();    // soft halo
      g.globalAlpha = 1; g.lineWidth = 2.2; g.stroke();                                 // the track
      const [ax, ay] = P(...pts[0]), [bx, by] = P(...pts[1]);                            // start/finish line
      const len = Math.hypot(bx - ax, by - ay) || 1, nx = -(by - ay) / len * 6, ny = (bx - ax) / len * 6;
      g.strokeStyle = accent; g.lineWidth = 3; g.beginPath(); g.moveTo(ax - nx, ay - ny); g.lineTo(ax + nx, ay + ny); g.stroke();
      if (!reduceMotion) {                                                              // a car lapping every 24 s
        const [cx2, cy2] = P(...pts[Math.floor((t / 24000 % 1) * n) % n]);
        g.fillStyle = accent; g.beginPath(); g.arc(cx2, cy2, 3.4, 0, 7); g.fill();
        g.strokeStyle = ink; g.lineWidth = 1.2; g.stroke();
      }
    }
    if (!loop) { loop = true; const tick = t2 => { paint(document, t2); setTimeout(() => requestAnimationFrame(tick), 40); }; requestAnimationFrame(tick); }
  }
  let loop = false;

  function skeleton(z) {
    const rows = z === "s" ? 2 : z === "m" ? 3 : 9;
    return `<div class="skel" style="width:40%"></div><div class="grow"></div>${z === "s" ? `<div class="skel h" style="width:60%;margin-bottom:10px"></div>` : ""}
      <div style="display:grid;gap:8px">${Array.from({ length: rows }, (_, i) => `<div class="skel" style="width:${[86, 72, 80, 64][i % 4]}%"></div>`).join("")}</div>`;
  }

  /** iOS lock screen accessory widgets (monochrome, vibrant). */
  function lock(v, now) {
    if (v.loading) return "";
    const ns = v.next_session, t = v.mode === "live" ? v.live : null;
    let rect, circ, inline;
    if (t) { rect = `<div class="a">● Live · ${esc(t.phase || sessionLabel(t.session_type))}${t.lap ? ` · L${t.lap}` : ""}</div><div class="b">${esc(t.rows[0]?.code ?? "")} <span style="opacity:.6;font-size:16px">${esc(t.rows[1]?.gap ?? "")}</span></div><div class="c">${t.rows.slice(0, 3).map(r => esc(r.code)).join(" ")}</div>`;
      circ = `<div class="a">LAP</div><div class="b">${t.lap ?? "—"}</div>`; inline = `● ${esc(t.rows[0]?.code ?? "")} leads${t.lap ? ` · L${t.lap}/${t.laps_total}` : ""}`; }
    else if (ns) { const p = parts(ns.starts_at, now);
      rect = `<div class="a">${esc(ns.label)} · ${esc(shortCountry(v.race))}</div><div class="b">${p.d ? `${pad(p.d)}d ` : ""}${pad(p.h)}:${pad(p.m)}:${pad(p.s)}</div><div class="c">${dayTime(ns.starts_at)}</div>`;
      circ = `<div class="a">${p.d ? "DAYS" : "HRS"}</div><div class="b">${p.d || pad(p.h)}</div>`; inline = `${esc(sessionLabel(ns.type))} ${dayTime(ns.starts_at)}`; }
    else return "";
    return `<div class="lk"><div class="lk-rect">${rect}</div><span class="lbl">Rectangular</span></div>
      <div class="lk"><div class="lk-circ">${circ}</div><span class="lbl">Circular</span></div>
      <div class="lk"><div class="lk-inline">${inline}</div><span class="lbl">Inline</span></div>`;
  }

  function render(id, z, v, now, opts) {
    O = opts;
    const team = hexColor(opts.snap?.driver?.team_color);
    const accent = opts.accent === "team" && team ? `--acc:${team};` : "";
    const cls = `w ${z} p-${opts.platform} th-${opts.theme}${opts.teamColors ? "" : " no-team"}`;
    const name = WIDGETS.find(w => w[0] === id)[1];
    const body = v.loading ? skeleton(z) : R[id](v, z, now);
    return `<div class="${cls}" style="${accent}" role="group" aria-label="${esc(name)} widget, ${({ s: "small", m: "medium", l: "large" })[z]}" aria-busy="${!!v.loading}">${body}</div>`;
  }

  /** Animate timing rows to their new places after a re-render (spec §25). */
  function flip(container, fn) {
    const before = new Map([...container.querySelectorAll(".tr[data-code]")].map(el => [el.closest(".w").className + el.dataset.code, el.getBoundingClientRect().top]));
    fn();
    for (const el of container.querySelectorAll(".tr[data-code]")) {
      const was = before.get(el.closest(".w").className + el.dataset.code);
      if (was == null) continue;
      const dy = was - el.getBoundingClientRect().top;
      if (Math.abs(dy) < 1) continue;
      el.style.transform = `translateY(${dy}px)`;
      requestAnimationFrame(() => { el.classList.add("moving"); el.style.transform = ""; });
    }
  }

  return { WIDGETS, render, flip, paint, lock, raceMode, stateOf, esc, ago, hexColor, silhouette, retry: () => {} };
})();
