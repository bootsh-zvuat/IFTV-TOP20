// ============ 基础枚举 ============

export type EventLevel =
  | 'Major'
  | '超级精英赛'
  | '精英赛'
  | '大型赛事'
  | '中型赛事'
  | '次级赛事'
  | '不纳入';

export type TeamPlacement = '冠军' | '亚军' | '四强' | '八强' | '小组淘汰';

export type HonorType = 'MVP' | 'EVP' | '无';

// ============ 数据模型 ============

export interface Player {
  id: string;
  name: string;
  team: string;
  year: number;
}

export interface Event {
  id: string;
  name: string;
  year: number;
  level: EventLevel;
  /** 用户可改；undefined 表示使用级别默认权重 */
  weight?: number;
}

export interface EventResult {
  eventId: string;
  playerId: string;
  teamPlacement: TeamPlacement;
  honor: HonorType;
  /** EVP 顺位 1/2/3；MVP 为 1；无荣誉为 0 */
  honorRank: number;
  rating: number;
  adr: number;
  kpr: number;
  /** 出场地图数（导入数据可能缺省；用于最小参赛量门槛） */
  maps?: number;
  /**
   * HLTV 对手强度：对阵 top-N 战队时的 Rating（Rating 3.0 口径）。
   * 来源为 HLTV 选手页（需经 Edge CDP 采集，见 fetch_hltv_opponents.py）；
   * 缺省表示该选手无此数据，此时对手强度通道对其不生效。
   * 注意：这是**选手年度聚合值**，同一选手在全年各赛事中相同。
   */
  vsTop5?: number;
  vsTop10?: number;
  vsTop20?: number;
  vsTop30?: number;
  vsTop50?: number;
}

export type OriginalMvpAction = '保持MVP' | '降为EVP' | '移除荣誉' | '转给他人';

export interface IfScenario {
  id: string;
  name: string;
  year: number;
  eventId: string;
  /** 新冠军队伍的选手（用于把冠军队伍整体调整为冠军） */
  newWinnerTeam: string;
  newMvpId: string;
  originalMvpAction: OriginalMvpAction;
  /** 原 MVP 降为 EVP 时的指定顺位（可选，缺省自动插入） */
  originalMvpEvpRank?: 1 | 2 | 3;
  evpMode: '手动' | '自动';
  manualEvp?: { playerId: string; rank: 1 | 2 | 3 }[];
  createdAt: number;
}

export interface RankingEntry {
  playerId: string;
  playerName: string;
  team: string;
  totalScore: number;
  rank: number;
}

export interface RankingSnapshot {
  id: string;
  year: number;
  /** 无则为原始算法排名 */
  scenarioId?: string;
  scenarioName?: string;
  algorithmVersion: string;
  createdAt: number;
  top20: RankingEntry[];
}

export interface HltvBaselineEntry {
  rank: number;
  playerName: string;
  playerId?: string;
}

export interface HltvBaseline {
  year: number;
  top20: HltvBaselineEntry[];
}

// ============ 权重配置 ============

export interface WeightConfig {
  eventLevelWeights: Record<EventLevel, number>;
  placementAdjust: Record<TeamPlacement, number>;
  honorBase: {
    MVP: number;
    EVP1: number;
    EVP2: number;
    EVP3: number;
    none: number;
    terrible: number;
  };
  /** rating 分档加分：rating 达到 threshold 即加 bonus（取命中的最高档）；
   *  below=true 为负分档：rating 低于 threshold 即扣 bonus（取命中的最重档） */
  ratingTiers: { threshold: number; bonus: number; below?: boolean }[];
  /** 最小年度出场图数：低于此值的选手不进入排名（无图数数据时不过滤） */
  minMaps: number;
  /** 单赛事最小图数：该赛事出场图数低于此值的记录不计分（防止替补/教练蹭冠军分） */
  minEventMaps: number;
  scoreMin: number;
  scoreMax: number;
  /**
   * HLTV 对手强度通道（v1.3.0 新增）。
   *
   * 数据：选手「对阵 top-N 战队时的 Rating」（HLTV Rating 3.0 口径），
   * 经 Edge CDP 采集（见 fetch_hltv_opponents.py）。
   *
   * 该信号**方向正确**：在官方 7-20 名段内，与官方名次的 Spearman
   * = −0.385(2025) / −0.473(2024)，强于现行总分（−0.336 / −0.196）。
   *
   * 但经严格跨年验证，**它无法改善中段 MAE**：
   *   中段 MAE 随 k 非单调波动（2025: 4.64→4.57→4.71→4.50），
   *   Top20 重叠无提升（保持 18/20、17/20），k≥5 后迅速恶化。
   * 因此默认 weight = 0（关闭）。开启前请先在真实数据上回测。
   *
   * 实现：选手年度 z-score（**只在有该数据的选手之间**归一化，
   * 无数据者不入池也不加分），乘权重后加到总分。
   * 不做逐赛事加权 —— 该值是年度聚合值，逐赛事加权等价于乘以场次。
   */
  opponentWeight: number;
  /** 使用哪一档 vs Top-N 作为对手强度信号 */
  opponentTier: 5 | 10 | 20 | 30 | 50;
}

// ============ 导入行 ============

export interface ImportedRow {
  year: number;
  eventName: string;
  eventLevel: EventLevel;
  eventWeight?: number;
  playerId: string;
  playerName: string;
  team: string;
  teamPlacement: TeamPlacement;
  honor: HonorType;
  honorRank: number;
  rating: number;
  adr: number;
  kpr: number;
  maps?: number;
  vsTop5?: number;
  vsTop10?: number;
  vsTop20?: number;
  vsTop30?: number;
  vsTop50?: number;
}
