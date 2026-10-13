// scripts/verify.ts
import { readFileSync } from "node:fs";

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
    { threshold: 1.1, bonus: 0.5 }
  ],
  minMaps: 20,
  minEventMaps: 3,
  scoreMin: -2,
  scoreMax: 11
};

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

// scripts/verify.ts
var data = JSON.parse(
  readFileSync(new URL("./verify-data.json", import.meta.url), "utf-8")
);
function spearman(a, b) {
  const n = a.length;
  const d2 = a.reduce((s, x, i) => s + (x - b[i]) ** 2, 0);
  return 1 - 6 * d2 / (n * (n * n - 1));
}
function evaluate(year, cfg, label) {
  const entries = computeRanking(year, data.events, data.results, data.players, cfg);
  const baseline = data.baselines[String(year)] ?? [];
  const rankOf = new Map(entries.map((e) => [e.playerId, e.rank]));
  const fallback = entries.length + 1;
  const officials = baseline.map((b) => b.rank);
  const preds = baseline.map((b) => rankOf.get(b.playerId) ?? fallback);
  const sp = spearman(officials, preds);
  const mae = preds.reduce((s, p, i) => s + Math.abs(p - officials[i]), 0) / preds.length;
  const predTop20 = new Set(entries.slice(0, 20).map((e) => e.playerId));
  const predTop5 = new Set(entries.slice(0, 5).map((e) => e.playerId));
  const overlap20 = baseline.filter((b) => predTop20.has(b.playerId)).length;
  const overlap5 = baseline.filter((b) => b.rank <= 5 && predTop5.has(b.playerId)).length;
  const missing = baseline.filter((b) => !rankOf.has(b.playerId)).map((b) => b.name);
  console.log(`
[${year}] ${label}: Spearman=${sp.toFixed(3)}  MAE=${mae.toFixed(2)}  Top20\u91CD\u53E0=${overlap20}/20  Top5\u91CD\u53E0=${overlap5}/5`);
  if (missing.length) console.log(`  \u65E0\u6570\u636E\u5B98\u65B9\u9009\u624B: ${missing.join(", ")}`);
  console.log("  \u540D\u6B21\u5BF9\u7167(\u5B98\u65B9\u2192\u9884\u6D4B): " + baseline.map((b, i) => `${b.name} ${b.rank}\u2192${preds[i]}`).join(" | "));
  console.log("  \u9884\u6D4BTop10: " + entries.slice(0, 10).map((e) => `${e.rank}.${e.playerName}(${e.totalScore})`).join(" "));
  return { sp, mae, overlap20, overlap5 };
}
for (const year of [2024, 2025]) {
  evaluate(year, DEFAULT_WEIGHTS, "\u7ECF\u9A8C\u9ED8\u8BA4");
  evaluate(year, FITTED_WEIGHTS, "\u62DF\u5408\u6821\u51C6");
}
