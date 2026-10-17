import type { EventResult } from '../types';
import { PLAYOFF_PLACEMENTS } from '../config/defaults';

/**
 * EVP 候选排序：
 * - 只考虑进入淘汰赛（冠军/亚军/四强/八强）队伍的选手
 * - 排除 exclude 中的选手（MVP 等）
 * - 按 Rating 降序，相同看 ADR
 */
export function rankEvpCandidates(eventResults: EventResult[], exclude: Set<string>): EventResult[] {
  return eventResults
    .filter((r) => !exclude.has(r.playerId) && PLAYOFF_PLACEMENTS.includes(r.teamPlacement))
    .sort((a, b) => b.rating - a.rating || b.adr - a.adr);
}

/**
 * 整体重排 EVP：排除 MVP 持有者后取候选前三名，依次获得 EVP 1/2/3。
 * 返回 playerId -> evpRank 的映射
 */
export function autoAssignEvp(
  eventResults: EventResult[],
  mvpPlayerId: string | null,
): Map<string, 1 | 2 | 3> {
  const result = new Map<string, 1 | 2 | 3>();
  rankEvpCandidates(eventResults, new Set(mvpPlayerId ? [mvpPlayerId] : []))
    .slice(0, 3)
    .forEach((r, i) => result.set(r.playerId, (i + 1) as 1 | 2 | 3));
  return result;
}
