// scripts/apex-check.ts
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
  // rating 分档加分：稳定输出（≥1.10）即有小分，明星档（≥1.30）重奖
  ratingTiers: [
    { threshold: 1.3, bonus: 2 },
    { threshold: 1.2, bonus: 1 },
    { threshold: 1.1, bonus: 0.5 }
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
  return rawRows.map((raw2, i) => {
    const line = i + 2;
    const level = str(raw2["\u8D5B\u4E8B\u7EA7\u522B"]);
    const placement = str(raw2["\u961F\u4F0D\u540D\u6B21"]);
    const honor = str(raw2["\u8363\u8A89\u7C7B\u578B"]) || "\u65E0";
    if (!LEVEL_SET.has(level)) throw new Error(`\u7B2C ${line} \u884C\uFF1A\u8D5B\u4E8B\u7EA7\u522B\u300C${level}\u300D\u65E0\u6548`);
    if (!PLACEMENT_SET.has(placement)) throw new Error(`\u7B2C ${line} \u884C\uFF1A\u961F\u4F0D\u540D\u6B21\u300C${placement}\u300D\u65E0\u6548`);
    if (!HONOR_SET.has(honor)) throw new Error(`\u7B2C ${line} \u884C\uFF1A\u8363\u8A89\u7C7B\u578B\u300C${honor}\u300D\u65E0\u6548`);
    const weight = str(raw2["\u8D5B\u4E8B\u6743\u91CD"]);
    return {
      year: num(raw2["\u5E74\u4EFD"]),
      eventName: str(raw2["\u8D5B\u4E8B\u540D\u79F0"]),
      eventLevel: level,
      eventWeight: weight === "" ? void 0 : num(weight),
      playerId: str(raw2["\u9009\u624BID"]) || str(raw2["\u9009\u624B\u540D"]),
      playerName: str(raw2["\u9009\u624B\u540D"]),
      team: str(raw2["\u961F\u4F0D"]),
      teamPlacement: placement,
      honor,
      honorRank: num(raw2["\u8363\u8A89\u987A\u4F4D"]),
      rating: num(raw2["Rating"]),
      adr: num(raw2["ADR"]),
      kpr: num(raw2["KPR"]),
      maps: num(raw2["\u5730\u56FE\u6570"]) || void 0
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
    if (rating >= t.threshold) bonus = Math.max(bonus, t.bonus);
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

// scripts/apex-check.ts
var wb = XLSX2.read(readFileSync(new URL("../../data/if_sim_2025_events.xlsx", import.meta.url)));
var raw = XLSX2.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]]);
var data = buildData(parseRows(raw));
var evMap = new Map(data.events.map((e) => [e.id, e]));
var mine = data.results.filter((r) => {
  const p = data.players.find((x) => x.id === r.playerId);
  return p?.name === "apEX" || p?.name === "flameZ" || p?.name === "frozen";
});
for (const name of ["apEX", "flameZ", "frozen"]) {
  const rs = mine.filter((r) => data.players.find((x) => x.id === r.playerId)?.name === name);
  let total = 0;
  console.log(`
=== ${name}\uFF08${rs.length} \u8D5B\u4E8B\uFF09===`);
  const byPlace = {};
  for (const r of rs.sort((a, b) => (evMap.get(a.eventId)?.name ?? "").localeCompare(evMap.get(b.eventId)?.name ?? ""))) {
    const ev = evMap.get(r.eventId);
    const w = eventWeight(ev, DEFAULT_WEIGHTS);
    const s = eventPerformanceScore(r, DEFAULT_WEIGHTS);
    total += s * w;
    byPlace[r.teamPlacement] = (byPlace[r.teamPlacement] ?? 0) + 1;
    console.log(
      `  ${ev.name.slice(0, 34).padEnd(36)} w=${w.toFixed(2)} rating=${r.rating.toFixed(2)}(+${ratingTierBonus(r.rating, DEFAULT_WEIGHTS)}) ${r.honor} ${r.teamPlacement} \u2192 ${s.toFixed(1)}\xD7${w.toFixed(2)}=${(s * w).toFixed(2)}`
    );
  }
  console.log(`  \u540D\u6B21\u5206\u5E03: ${JSON.stringify(byPlace)}  \u603B\u5206 ${total.toFixed(2)}`);
}
