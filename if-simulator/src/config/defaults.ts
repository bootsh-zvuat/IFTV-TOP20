import type { WeightConfig } from '../types';

export const ALGORITHM_VERSION = '1.3.0';

export const DEFAULT_WEIGHTS: WeightConfig = {
  eventLevelWeights: {
    Major: 1.0,
    超级精英赛: 0.8,
    精英赛: 0.75,
    大型赛事: 0.65,
    中型赛事: 0.5,
    次级赛事: 0.45,
    不纳入: 0,
  },
  // v2（2025 真实数据校准，26 赛事网格搜索：Top20 重叠 19/20、Spearman 0.70）：
  // 名次通道正负重排——夺冠本身有正分，小组出局轻罚而非重罚，
  // 消除"无荣誉选手参赛越多扣越多、低样本路人霸榜"的问题
  placementAdjust: {
    冠军: 2,
    亚军: 0.5,
    四强: 0,
    八强: -0.5,
    小组淘汰: -1,
  },
  honorBase: {
    MVP: 10,
    EVP1: 8,
    EVP2: 6,
    EVP3: 4,
    none: 0,
    terrible: -1,
  },
  // rating 分档加分：稳定输出（≥1.10）即有小分，明星档（≥1.30）重奖；
  // v1.2.0 新增负分档（<1.05 / <1.00）——低 rating 不再零成本，
  // 抑制指挥/角色球员纯靠队伍名次分进榜（如 apEX 8 冠 +13 分但 rating 均值 ~0.98）
  ratingTiers: [
    { threshold: 1.3, bonus: 2 },
    { threshold: 1.2, bonus: 1 },
    { threshold: 1.1, bonus: 0.5 },
    { threshold: 1.05, bonus: -0.5, below: true },
    { threshold: 1.0, bonus: -1, below: true },
  ],
  minMaps: 20,
  minEventMaps: 3,
  scoreMin: -2,
  scoreMax: 11,
  // v1.3.0：HLTV 对手强度通道。
  // 重要：默认 **关闭**（0）。经修正后的严格验证（2026-10-13），
  // 该通道在中段（7-20 名）上**没有稳定的跨年改善**：
  // 中段 MAE 随 k 波动（2025: 4.64→4.57→4.71→4.50，非单调），
  // Top20 重叠始终 18/20（2025）与 17/20（2024）未见提升，
  // 且 k≥5 后迅速恶化。此前"改善到 3.86/4.14、Top20 20/20"的结论
  // 来自一个有缺陷的原型（z-score 池误含 151 个无数据的 0 值），已作废。
  // 信号本身方向正确（中段 Spearman −0.385/−0.473），但不足以改善 MAE。
  // 保留该通道供用户自行实验；开启前请先用真实数据回测。
  opponentWeight: 0,
  opponentTier: 5,
};

/**
 * 拟合校准预设（数据来源：项目根目录 fit_ranking.py，2021-2025 训练，
 * 留一年验证 Spearman 0.732 / MAE 2.97 名，详见 fitted_params.json）。
 *
 * 拟合模型是"年度聚合 z-score"结构，与本模拟器"逐赛事加和"结构不同，
 * 只有比例关系可直接移植：
 * - EVP = 0.50 × MVP（拟合 evp_ratio=0.4953）→ MVP=10 时 EVP 统一 5 分；
 *   拟合数据无法区分 EVP 顺位，故 EVP1/2/3 不再设梯度
 * - Major MVP = 1.59×、超级精英赛（卡托/科隆）MVP = 1.46× 普通赛事
 *   （拟合 m_major=1.5941 / m_super=1.4631）→ 以大型赛事 0.65 为基准换算
 * - 拟合中表现分权重 ≈ 荣誉分权重（0.46 vs 0.46），rating 为表现分主导（0.56）
 *   → rating 采用 1.1/1.2/1.3 三档加分（经验校准，非直接拟合参数）
 * - 队伍成绩调整：名次分（冠军 +2 … 小组淘汰 -2）为 2025 真实数据经验校准，
 *   拟合模型的 z-score 名次分量纲不可直接移植
 * - 精英赛/中型/次级赛事层级：拟合仅校准 Major/超精英/普通三档，保持原梯度
 */
export const FITTED_WEIGHTS: WeightConfig = {
  eventLevelWeights: {
    Major: 1.05,
    超级精英赛: 0.95,
    精英赛: 0.75,
    大型赛事: 0.65,
    中型赛事: 0.5,
    次级赛事: 0.45,
    不纳入: 0,
  },
  placementAdjust: {
    冠军: 2,
    亚军: 0.5,
    四强: 0,
    八强: -0.5,
    小组淘汰: -1,
  },
  honorBase: {
    MVP: 10,
    EVP1: 5,
    EVP2: 5,
    EVP3: 5,
    none: 0,
    terrible: -1,
  },
  ratingTiers: [
    { threshold: 1.3, bonus: 2 },
    { threshold: 1.2, bonus: 1 },
    { threshold: 1.1, bonus: 0.5 },
    { threshold: 1.05, bonus: -0.5, below: true },
    { threshold: 1.0, bonus: -1, below: true },
  ],
  minMaps: 20,
  minEventMaps: 3,
  scoreMin: -2,
  scoreMax: 11,
  // 该预设同样默认关闭对手强度通道（原因见 DEFAULT_WEIGHTS 的注释）
  opponentWeight: 0,
  opponentTier: 5,
};

/** 权重预设：经验默认 / 拟合校准 */
export const WEIGHT_PRESETS = [
  {
    id: 'default',
    name: '经验默认',
    // 2025 回测：Top20 重叠 18/20、头部（1-6 名）全中、中段 Spearman +0.34
    note: '推荐；顶部 If 线最准',
    weights: DEFAULT_WEIGHTS,
  },
  {
    id: 'fitted',
    name: '拟合校准(2021-2025)',
    // 实测该预设中段更差：2025 中段 MAE 4.57 → 5.00、Top20 重叠 18 → 17。
    // 拟合模型是"年度聚合 z-score"结构，与模拟器的逐赛事加和结构不同，
    // 只有比例关系可移植，故不保证逐名次精度。
    note: '结构不同，不保证中段精度',
    weights: FITTED_WEIGHTS,
  },
] as const;

export const EVENT_LEVELS = [
  'Major',
  '超级精英赛',
  '精英赛',
  '大型赛事',
  '中型赛事',
  '次级赛事',
  '不纳入',
] as const;

export const TEAM_PLACEMENTS = ['冠军', '亚军', '四强', '八强', '小组淘汰'] as const;

export const HONOR_TYPES = ['MVP', 'EVP', '无'] as const;

/** 进入淘汰赛的名次（自动 EVP 重排只考虑这些选手），八强起算 */
export const PLAYOFF_PLACEMENTS: readonly string[] = ['冠军', '亚军', '四强', '八强'];
