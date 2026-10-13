// scripts/import-check-2024.ts
import { readFileSync } from "node:fs";
import * as XLSX2 from "xlsx";

// src/core/excel.ts
import * as XLSX from "xlsx";

// src/config/defaults.ts
var DEFAULT_WEIGHTS = {
  eventLevelWeights: {
    Major: 1,
    \u8D85\u7EA7\u7CBE\u82F1\u8D5B: 0.8,
    \u7CBE\u82F1\u8D5B: 0.75,
    \u5927\u578B\u8D5B\u4E8B: 0.65,
    \u4E2D\u578B\u8D5B\u4E8B: 0.5,
    \u6B21\u7EA7\u8D5B\u4E8B: 0.45,
    \u4E0D\u7EB3\u5165: 0
  },
  // v2（2025 真实数据校准，26 赛事网格搜索：Top20 重叠 19/20、Spearman 0.70）：
  // 名次通道正负重排——夺冠本身有正分，小组出局轻罚而非重罚，
  // 消除"无荣誉选手参赛越多扣越多、低样本路人霸榜"的问题
  placementAdjust: {
    \u51A0\u519B: 2,
    \u4E9A\u519B: 0.5,
    \u56DB\u5F3A: 0,
    \u516B\u5F3A: -0.5,
    \u5C0F\u7EC4\u6DD8\u6C70: -1
  },
  honorBase: {
    MVP: 10,
    EVP1: 8,
    EVP2: 6,
    EVP3: 4,
    none: 0,
    terrible: -1
  },
  // rating 分档加分：稳定输出（≥1.10）即有小分，明星档（≥1.30）重奖；
  // v1.2.0 新增负分档（<1.05 / <1.00）——低 rating 不再零成本，
  // 抑制指挥/角色球员纯靠队伍名次分进榜（如 apEX 8 冠 +13 分但 rating 均值 ~0.98）
  ratingTiers: [
    { threshold: 1.3, bonus: 2 },
    { threshold: 1.2, bonus: 1 },
    { threshold: 1.1, bonus: 0.5 },
    { threshold: 1.05, bonus: -0.5, below: true },
    { threshold: 1, bonus: -1, below: true }
  ],
  minMaps: 20,
  minEventMaps: 3,
  scoreMin: -2,
  scoreMax: 11
};
var FITTED_WEIGHTS = {
  eventLevelWeights: {
    Major: 1.05,
    \u8D85\u7EA7\u7CBE\u82F1\u8D5B: 0.95,
    \u7CBE\u82F1\u8D5B: 0.75,
    \u5927\u578B\u8D5B\u4E8B: 0.65,
    \u4E2D\u578B\u8D5B\u4E8B: 0.5,
    \u6B21\u7EA7\u8D5B\u4E8B: 0.45,
    \u4E0D\u7EB3\u5165: 0
  },
  placementAdjust: {
    \u51A0\u519B: 2,
    \u4E9A\u519B: 0.5,
    \u56DB\u5F3A: 0,
    \u516B\u5F3A: -0.5,
    \u5C0F\u7EC4\u6DD8\u6C70: -1
  },
  honorBase: {
    MVP: 10,
    EVP1: 5,
    EVP2: 5,
    EVP3: 5,
    none: 0,
    terrible: -1
  },
  ratingTiers: [
    { threshold: 1.3, bonus: 2 },
    { threshold: 1.2, bonus: 1 },
    { threshold: 1.1, bonus: 0.5 },
    { threshold: 1.05, bonus: -0.5, below: true },
    { threshold: 1, bonus: -1, below: true }
  ],
  minMaps: 20,
  minEventMaps: 3,
  scoreMin: -2,
  scoreMax: 11
};

// src/core/excel.ts
var LEVEL_SET = /* @__PURE__ */ new Set([
  "Major",
  "\u8D85\u7EA7\u7CBE\u82F1\u8D5B",
  "\u7CBE\u82F1\u8D5B",
  "\u5927\u578B\u8D5B\u4E8B",
  "\u4E2D\u578B\u8D5B\u4E8B",
  "\u6B21\u7EA7\u8D5B\u4E8B",
  "\u4E0D\u7EB3\u5165"
]);
var PLACEMENT_SET = /* @__PURE__ */ new Set(["\u51A0\u519B", "\u4E9A\u519B", "\u56DB\u5F3A", "\u516B\u5F3A", "\u5C0F\u7EC4\u6DD8\u6C70"]);
var HONOR_SET = /* @__PURE__ */ new Set(["MVP", "EVP", "\u65E0"]);
function str(v) {
  return v === void 0 || v === null ? "" : String(v).trim();
}
function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function parseRows(rawRows) {
  return rawRows.map((raw, i) => {
    const line = i + 2;
    const level = str(raw["\u8D5B\u4E8B\u7EA7\u522B"]);
    const placement = str(raw["\u961F\u4F0D\u540D\u6B21"]);
    const honor = str(raw["\u8363\u8A89\u7C7B\u578B"]) || "\u65E0";
    if (!LEVEL_SET.has(level)) throw new Error(`\u7B2C ${line} \u884C\uFF1A\u8D5B\u4E8B\u7EA7\u522B\u300C${level}\u300D\u65E0\u6548`);
    if (!PLACEMENT_SET.has(placement)) throw new Error(`\u7B2C ${line} \u884C\uFF1A\u961F\u4F0D\u540D\u6B21\u300C${placement}\u300D\u65E0\u6548`);
    if (!HONOR_SET.has(honor)) throw new Error(`\u7B2C ${line} \u884C\uFF1A\u8363\u8A89\u7C7B\u578B\u300C${honor}\u300D\u65E0\u6548`);
    const weight = str(raw["\u8D5B\u4E8B\u6743\u91CD"]);
    return {
      year: num(raw["\u5E74\u4EFD"]),
      eventName: str(raw["\u8D5B\u4E8B\u540D\u79F0"]),
      eventLevel: level,
      eventWeight: weight === "" ? void 0 : num(weight),
      playerId: str(raw["\u9009\u624BID"]) || str(raw["\u9009\u624B\u540D"]),
      playerName: str(raw["\u9009\u624B\u540D"]),
      team: str(raw["\u961F\u4F0D"]),
      teamPlacement: placement,
      honor,
      honorRank: num(raw["\u8363\u8A89\u987A\u4F4D"]),
      rating: num(raw["Rating"]),
      adr: num(raw["ADR"]),
      kpr: num(raw["KPR"]),
      maps: num(raw["\u5730\u56FE\u6570"]) || void 0
    };
  });
}
function buildData(rows) {
  const players = /* @__PURE__ */ new Map();
  const events = /* @__PURE__ */ new Map();
  const results = [];
  for (const r of rows) {
    const eventId = `${r.year}::${r.eventName}`;
    if (!events.has(eventId)) {
      events.set(eventId, {
        id: eventId,
        name: r.eventName,
        year: r.year,
        level: r.eventLevel,
        weight: r.eventWeight
      });
    }
    const pid = `${r.year}::${r.playerId}`;
    if (!players.has(pid)) {
      players.set(pid, { id: pid, name: r.playerName, team: r.team, year: r.year });
    }
    results.push({
      eventId,
      playerId: pid,
      teamPlacement: r.teamPlacement,
      honor: r.honor,
      honorRank: r.honor === "MVP" ? 1 : r.honor === "EVP" ? r.honorRank : 0,
      rating: r.rating,
      adr: r.adr,
      kpr: r.kpr,
      maps: r.maps
    });
  }
  return { players: [...players.values()], events: [...events.values()], results };
}

// src/core/score.ts
function honorBaseScore(result, cfg) {
  if (result.honor === "MVP") return cfg.honorBase.MVP;
  if (result.honor === "EVP") {
    if (result.honorRank === 1) return cfg.honorBase.EVP1;
    if (result.honorRank === 2) return cfg.honorBase.EVP2;
    if (result.honorRank === 3) return cfg.honorBase.EVP3;
  }
  return cfg.honorBase.none;
}
function ratingTierBonus(rating, cfg) {
  let bonus = 0;
  for (const t of cfg.ratingTiers ?? []) {
    if (t.below) {
      if (rating < t.threshold) bonus = Math.min(bonus, t.bonus);
    } else if (rating >= t.threshold) {
      bonus = Math.max(bonus, t.bonus);
    }
  }
  return bonus;
}
function eventPerformanceScore(result, cfg) {
  const score = honorBaseScore(result, cfg) + ratingTierBonus(result.rating, cfg) + (cfg.placementAdjust[result.teamPlacement] ?? 0);
  return Math.min(cfg.scoreMax, Math.max(cfg.scoreMin, score));
}

// src/core/ranking.ts
function eventWeight(event, cfg) {
  return event.weight ?? cfg.eventLevelWeights[event.level] ?? 0;
}
function computeRanking(year, events, results, players, cfg) {
  const yearEvents = events.filter((e) => e.year === year);
  const eventMap = new Map(yearEvents.map((e) => [e.id, e]));
  const totals = /* @__PURE__ */ new Map();
  const mapsSum = /* @__PURE__ */ new Map();
  let hasMapData = false;
  const minEventMaps = cfg.minEventMaps ?? 0;
  for (const r of results) {
    const ev = eventMap.get(r.eventId);
    if (!ev) continue;
    if (typeof r.maps === "number") hasMapData = true;
    if (typeof r.maps === "number" && minEventMaps > 0 && r.maps < minEventMaps) continue;
    mapsSum.set(r.playerId, (mapsSum.get(r.playerId) ?? 0) + (r.maps ?? 0));
    const w = eventWeight(ev, cfg);
    if (w === 0) continue;
    const s = eventPerformanceScore(r, cfg);
    totals.set(r.playerId, (totals.get(r.playerId) ?? 0) + s * w);
  }
  const minMaps = cfg.minMaps ?? 0;
  const playerMap = new Map(players.map((p) => [p.id, p]));
  const entries = [];
  for (const [playerId, totalScore] of totals) {
    if (hasMapData && minMaps > 0 && (mapsSum.get(playerId) ?? 0) < minMaps) continue;
    const p = playerMap.get(playerId);
    entries.push({
      playerId,
      playerName: p?.name ?? playerId,
      team: p?.team ?? "",
      totalScore: Math.round(totalScore * 100) / 100,
      rank: 0
    });
  }
  entries.sort((a, b) => b.totalScore - a.totalScore || a.playerName.localeCompare(b.playerName));
  entries.forEach((e, i) => e.rank = i + 1);
  return entries;
}

// scripts/import-check-2024.ts
var BASE = new URL("../../data/", import.meta.url);
function loadXlsx(name) {
  const wb = XLSX2.read(readFileSync(new URL(name, BASE)));
  return XLSX2.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]]);
}
for (const year of [2024]) {
  const rawEvents = loadXlsx(`if_sim_${year}_events.xlsx`);
  const data = buildData(parseRows(rawEvents));
  console.log(`
[${year}] \u8D5B\u4E8B\u6570\u636E\uFF1A${data.events.length} \u8D5B\u4E8B / ${data.players.length} \u9009\u624B / ${data.results.length} \u7ED3\u679C`);
  const rawBase = loadXlsx(`if_sim_${year}_baseline.xlsx`);
  const baseline = rawBase.map((r) => ({ rank: Number(r["\u540D\u6B21"]), name: String(r["\u9009\u624B\u540D"]).trim() })).sort((a, b) => a.rank - b.rank);
  for (const [label, cfg] of [["\u7ECF\u9A8C\u9ED8\u8BA4", DEFAULT_WEIGHTS], ["\u62DF\u5408\u6821\u51C6", FITTED_WEIGHTS]]) {
    const entries = computeRanking(year, data.events, data.results, data.players, cfg);
    const byName = new Map(entries.map((e) => [e.playerName, e.rank]));
    const lines = baseline.map((b) => `${b.rank}.${b.name}\u2192${byName.get(b.name) ?? "\u699C\u5916"}`);
    const overlaps = baseline.filter((b) => byName.has(b.name));
    const sp = baseline.filter((b) => byName.has(b.name)).length;
    console.log(`[${label}] \u9884\u6D4BTop20: ${entries.slice(0, 20).map((e) => `${e.rank}.${e.playerName}`).join(" ")}`);
    console.log(`[${label}] \u5B98\u65B9\u2192\u9884\u6D4B: ${lines.join(" | ")}`);
    console.log(`[${label}] Top20 \u91CD\u53E0 ${sp}/20\uFF0C\u5B98\u65B9\u5728\u699C\u5185: ${overlaps.map((b) => b.name).join(", ")}`);
    console.log(`[${label}] \u5B98\u65B9\u699C\u5916\u4EBA: ${baseline.filter((b) => !byName.has(b.name)).map((b) => b.name).join(", ")}`);
  }
}
