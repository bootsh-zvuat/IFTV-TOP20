import type { EventResult } from '../types';
import { PLAYOFF_PLACEMENTS } from '../config/defaults';

/**
 * 自动重排 EVP：
 * - 只考虑进入淘汰赛（冠军/亚军/四强/八强）队伍的选手
 * - 排除 MVP 持有者
 * - 按 Rating 降序，相同看 ADR
 * - 前三名依次获得 EVP 1/2/3
 * 返回 playerId -> evpRank 的映射
 */
export function autoAssignEvp(
  eventResults: EventResult[],
  mvpPlayerId: string | null,
): Map<string, 1 | 2 | 3> {
  const candidates = eventResults.filter(
    (r) => r.playerId !== mvpPlayerId && PLAYOFF_PLACEMENTS.includes(r.teamPlacement),
  );
  candidates.sort((a, b) => {
    if (b.rating !== a.rating) return b.rating - a.rating;
    return b.adr - a.adr;
  });
  const result = new Map<string, 1 | 2 | 3>();
  for (let i = 0; i < Math.min(3, candidates.length); i++) {
    result.set(candidates[i].playerId, (i + 1) as 1 | 2 | 3);
  }
  return result;
}
