import Dexie, { type Table } from 'dexie';
import { ALGORITHM_VERSION } from '../config/defaults';
import type {
  Event,
  EventResult,
  HltvBaseline,
  IfScenario,
  Player,
  RankingSnapshot,
  WeightConfig,
} from '../types';

interface WeightRecord {
  id: string; // 固定 'default'
  config: WeightConfig;
  /** 保存时的算法版本；版本不一致（计分语义变更）时弃用旧配置 */
  version?: string;
}

class IfSimulatorDB extends Dexie {
  players!: Table<Player, string>;
  events!: Table<Event, string>;
  results!: Table<EventResult, string>;
  scenarios!: Table<IfScenario, string>;
  snapshots!: Table<RankingSnapshot, string>;
  baselines!: Table<HltvBaseline, number>;
  weights!: Table<WeightRecord, string>;

  constructor() {
    super('if-simulator');
    this.version(1).stores({
      players: 'id, year',
      events: 'id, year',
      results: '++id, eventId, playerId',
      scenarios: 'id, year, eventId, createdAt',
      snapshots: 'id, year, scenarioId, createdAt',
      baselines: 'year',
      weights: 'id',
    });
  }
}

export const db = new IfSimulatorDB();

// ---- 权重配置 ----
export async function loadWeights(fallback: WeightConfig): Promise<WeightConfig> {
  const rec = await db.weights.get('default');
  if (!rec?.config) return fallback;
  // 计分语义随算法版本变化（如 v1.1 名次分/分档/门槛重排），旧版本配置直接弃用，
  // 避免旧的名次罚分覆盖新默认值
  if (rec.version !== ALGORITHM_VERSION) return fallback;
  // 同版本内仍做嵌套合并，兼容小版本新增字段
  const c = rec.config;
  return {
    ...fallback,
    ...c,
    eventLevelWeights: { ...fallback.eventLevelWeights, ...c.eventLevelWeights },
    placementAdjust: { ...fallback.placementAdjust, ...c.placementAdjust },
    honorBase: { ...fallback.honorBase, ...c.honorBase },
    ratingTiers: c.ratingTiers ?? fallback.ratingTiers,
    minMaps: c.minMaps ?? fallback.minMaps,
    minEventMaps: c.minEventMaps ?? fallback.minEventMaps,
    // v1.3.0 新增：老配置缺这两个字段时用默认值（版本号已挡掉跨版本配置，
    // 这里兜底同版本内的小版本升级）
    opponentWeight: c.opponentWeight ?? fallback.opponentWeight,
    opponentTier: c.opponentTier ?? fallback.opponentTier,
  };
}
export async function saveWeights(config: WeightConfig): Promise<void> {
  await db.weights.put({ id: 'default', config, version: ALGORITHM_VERSION });
}

// ---- 数据导入（整批替换对应年份数据） ----
export async function replaceYearData(
  years: number[],
  players: Player[],
  events: Event[],
  results: EventResult[],
): Promise<void> {
  await db.transaction('rw', [db.players, db.events, db.results], async () => {
    for (const y of years) {
      await db.players.where('year').equals(y).delete();
      const evIds = (await db.events.where('year').equals(y).toArray()).map((e) => e.id);
      await db.events.where('year').equals(y).delete();
      for (const id of evIds) await db.results.where('eventId').equals(id).delete();
    }
    await db.players.bulkPut(players);
    await db.events.bulkPut(events);
    await db.results.bulkPut(results as (EventResult & { id?: number })[]);
  });
}

export async function listYears(): Promise<number[]> {
  const years = new Set<number>();
  await db.events.each((e) => years.add(e.year));
  return [...years].sort((a, b) => b - a);
}

export async function yearData(year: number) {
  const events = await db.events.where('year').equals(year).toArray();
  const eventIds = new Set(events.map((e) => e.id));
  const results = (await db.results.toArray()).filter((r) => eventIds.has(r.eventId));
  const players = await db.players.where('year').equals(year).toArray();
  return { events, results, players };
}

// ---- 存档导出 / 导入 ----
export async function exportAll(): Promise<string> {
  const data = {
    players: await db.players.toArray(),
    events: await db.events.toArray(),
    results: await db.results.toArray(),
    scenarios: await db.scenarios.toArray(),
    snapshots: await db.snapshots.toArray(),
    baselines: await db.baselines.toArray(),
    weights: await db.weights.toArray(),
  };
  return JSON.stringify(data, null, 2);
}

export async function importAll(json: string): Promise<void> {
  const data = JSON.parse(json);
  // 存档是完整导出：先清空存档里包含的表再写入。直接 bulkPut 会和现有数据叠加——
  // results 用自增 id，重新导入过 Excel 后 id 不同，同一条成绩会出现两份、分数翻倍
  const restore = async <T, K>(table: Table<T, K>, rows: unknown) => {
    if (!Array.isArray(rows)) return;
    await table.clear();
    await table.bulkPut(rows as T[]);
  };
  await db.transaction(
    'rw',
    [db.players, db.events, db.results, db.scenarios, db.snapshots, db.baselines, db.weights],
    async () => {
      await restore(db.players, data.players);
      await restore(db.events, data.events);
      await restore(db.results, data.results);
      await restore(db.scenarios, data.scenarios);
      await restore(db.snapshots, data.snapshots);
      await restore(db.baselines, data.baselines);
      await restore(db.weights, data.weights);
    },
  );
}
