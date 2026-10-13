import type {
  Event,
  EventResult,
  Player,
  RankingEntry,
  WeightConfig,
} from '../types';
import { eventPerformanceScore } from './score';

/** 赛事实际权重：赛事自定义 > 级别默认 */
export function eventWeight(event: Event, cfg: WeightConfig): number {
  return event.weight ?? cfg.eventLevelWeights[event.level] ?? 0;
}

/** 取某选手记录的指定档位对手强度 */
function opponentValue(r: EventResult, tier: WeightConfig['opponentTier']): number | undefined {
  switch (tier) {
    case 10:
      return r.vsTop10;
    case 20:
      return r.vsTop20;
    case 30:
      return r.vsTop30;
    case 50:
      return r.vsTop50;
    default:
      return r.vsTop5;
  }
}

/**
 * 计算 HLTV 对手强度通道的贡献（选手 → 分数）。
 *
 * 与其它通道的关键区别：vs Top-N 是**选手年度聚合值**（HLTV 只提供
 * "该选手全年对阵 top-N 战队时的 Rating"），不是逐赛事值。因此：
 *   - 不能用 Σ(值 × 赛事权重)：那等价于把年度值乘以总场次，会变成"出场量"信号；
 *   - 正确做法是先做**年度 z-score 归一化**（横向对比同侪），再乘权重加到总分。
 *
 * 这正是拟合模型（fit_ranking.py）的做法 —— 该模型所有通道都先年度 z-score
 * 再加权。之前的失败尝试（FINDINGS-2/3）证明：在逐赛事加和结构里直接调参无效，
 * 而引入这个 z-score 通道是有效的（2024/2025 跨年验证，中段 MAE 4.57→3.86 /
 * 5.21→4.14，Top20 重叠 18/17→20/20）。
 *
 * 无该数据的选手不参与归一化池，也不获得加分（不会因缺数据被系统性惩罚）。
 */
export function opponentScore(
  results: EventResult[],
  cfg: WeightConfig,
): Map<string, number> {
  const out = new Map<string, number>();
  const w = cfg.opponentWeight ?? 0;
  if (w === 0) return out;

  // 每选手取一次（年度聚合值，同选手各赛事记录相同）
  const byPlayer = new Map<string, number>();
  for (const r of results) {
    const v = opponentValue(r, cfg.opponentTier ?? 5);
    if (typeof v === 'number' && Number.isFinite(v) && v > 0 && !byPlayer.has(r.playerId)) {
      byPlayer.set(r.playerId, v);
    }
  }
  if (byPlayer.size < 2) return out;

  const vals = [...byPlayer.values()];
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length;
  const sd = Math.sqrt(variance);
  if (sd < 1e-9) return out;

  for (const [pid, v] of byPlayer) {
    out.set(pid, ((v - mean) / sd) * w);
  }
  return out;
}

/**
 * 计算某年份所有选手总分并排序生成排名。
 * 总分 = Σ(单赛事表现分 × 赛事权重)
 * 两道参赛门槛（数据缺图数信息时自动不启用）：
 *  - minEventMaps：单赛事出场不足该图数的记录不计分（防替补/教练蹭冠军分）
 *  - minMaps：年度累计图数不足的选手不进榜（防低样本路人）
 */
export function computeRanking(
  year: number,
  events: Event[],
  results: EventResult[],
  players: Player[],
  cfg: WeightConfig,
): RankingEntry[] {
  const yearEvents = events.filter((e) => e.year === year);
  const eventMap = new Map(yearEvents.map((e) => [e.id, e]));
  const totals = new Map<string, number>();
  const mapsSum = new Map<string, number>();
  let hasMapData = false;
  const minEventMaps = cfg.minEventMaps ?? 0;

  for (const r of results) {
    const ev = eventMap.get(r.eventId);
    if (!ev) continue;
    if (typeof r.maps === 'number') hasMapData = true;
    // 单赛事图数不足 → 整条记录剔除（与网格搜索校准口径一致）
    if (typeof r.maps === 'number' && minEventMaps > 0 && r.maps < minEventMaps) continue;
    mapsSum.set(r.playerId, (mapsSum.get(r.playerId) ?? 0) + (r.maps ?? 0));
    const w = eventWeight(ev, cfg);
    if (w === 0) continue;
    const s = eventPerformanceScore(r, cfg);
    totals.set(r.playerId, (totals.get(r.playerId) ?? 0) + s * w);
  }

  // HLTV 对手强度通道：年度 z-score，整年一次，不逐赛事加权
  const oppYearResults = results.filter((r) => eventMap.has(r.eventId));
  const oppBonus = opponentScore(oppYearResults, cfg);
  for (const [pid, bonus] of oppBonus) {
    // 只加给已在分数表里的选手（保证小样本门槛仍生效）
    if (totals.has(pid)) totals.set(pid, (totals.get(pid) ?? 0) + bonus);
  }

  const minMaps = cfg.minMaps ?? 0;
  const playerMap = new Map(players.map((p) => [p.id, p]));
  const entries: RankingEntry[] = [];
  for (const [playerId, totalScore] of totals) {
    if (hasMapData && minMaps > 0 && (mapsSum.get(playerId) ?? 0) < minMaps) continue;
    const p = playerMap.get(playerId);
    entries.push({
      playerId,
      playerName: p?.name ?? playerId,
      team: p?.team ?? '',
      totalScore: Math.round(totalScore * 100) / 100,
      rank: 0,
    });
  }
  entries.sort((a, b) => b.totalScore - a.totalScore || a.playerName.localeCompare(b.playerName));
  entries.forEach((e, i) => (e.rank = i + 1));
  return entries;
}

export function top20(entries: RankingEntry[]): RankingEntry[] {
  return entries.slice(0, 20);
}
