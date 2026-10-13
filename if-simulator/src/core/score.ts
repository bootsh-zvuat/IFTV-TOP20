import type { EventResult, WeightConfig } from '../types';

/** 荣誉基础分 */
export function honorBaseScore(result: EventResult, cfg: WeightConfig): number {
  if (result.honor === 'MVP') return cfg.honorBase.MVP;
  if (result.honor === 'EVP') {
    if (result.honorRank === 1) return cfg.honorBase.EVP1;
    if (result.honorRank === 2) return cfg.honorBase.EVP2;
    if (result.honorRank === 3) return cfg.honorBase.EVP3;
  }
  return cfg.honorBase.none;
}

/**
 * rating 分档加分：正分档取所有命中档位中的最高分；below 负分档取最重扣分。
 * 例如 [{1.3,+2},{1.2,+1},{1.1,+0.5},{1.05,-0.5,below},{1.0,-1,below}]，
 * rating=1.25 → +1；rating=0.95 → -1。
 */
export function ratingTierBonus(rating: number, cfg: WeightConfig): number {
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

/**
 * 单赛事表现分 = 荣誉基础分 + rating 分档加分 + 队伍名次分
 * 结果截断到 [scoreMin, scoreMax]
 */
export function eventPerformanceScore(result: EventResult, cfg: WeightConfig): number {
  const score =
    honorBaseScore(result, cfg) +
    ratingTierBonus(result.rating, cfg) +
    (cfg.placementAdjust[result.teamPlacement] ?? 0);
  return Math.min(cfg.scoreMax, Math.max(cfg.scoreMin, score));
}
