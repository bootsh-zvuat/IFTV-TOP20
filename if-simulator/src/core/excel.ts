import * as XLSX from 'xlsx';
import type {
  Event,
  EventLevel,
  EventResult,
  HonorType,
  HltvBaseline,
  ImportedRow,
  Player,
  TeamPlacement,
} from '../types';
import { DEFAULT_WEIGHTS } from '../config/defaults';

const LEVEL_SET = new Set<string>([
  'Major', '超级精英赛', '精英赛', '大型赛事', '中型赛事', '次级赛事', '不纳入',
]);
const PLACEMENT_SET = new Set<string>(['冠军', '亚军', '四强', '八强', '小组淘汰']);
const HONOR_SET = new Set<string>(['MVP', 'EVP', '无']);

function str(v: unknown): string {
  return v === undefined || v === null ? '' : String(v).trim();
}
function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** 解析赛事数据 sheet 行为 ImportedRow（带校验，非法行抛出带行号的错误） */
export function parseRows(rawRows: Record<string, unknown>[]): ImportedRow[] {
  return rawRows.map((raw, i) => {
    const line = i + 2; // Excel 行号（含表头）
    const level = str(raw['赛事级别']);
    const placement = str(raw['队伍名次']);
    const honor = str(raw['荣誉类型']) || '无';
    if (!LEVEL_SET.has(level)) throw new Error(`第 ${line} 行：赛事级别「${level}」无效`);
    if (!PLACEMENT_SET.has(placement)) throw new Error(`第 ${line} 行：队伍名次「${placement}」无效`);
    if (!HONOR_SET.has(honor)) throw new Error(`第 ${line} 行：荣誉类型「${honor}」无效`);
    const weight = str(raw['赛事权重']);
    // HLTV 对手强度列（可选）：空值 → undefined，表示该选手无此数据
    const optNum = (v: unknown): number | undefined => {
      const s = str(v);
      if (s === '') return undefined;
      const n = Number(s);
      return Number.isFinite(n) && n > 0 ? n : undefined;
    };
    return {
      year: num(raw['年份']),
      eventName: str(raw['赛事名称']),
      eventLevel: level as EventLevel,
      eventWeight: weight === '' ? undefined : num(weight),
      playerId: str(raw['选手ID']) || str(raw['选手名']),
      playerName: str(raw['选手名']),
      team: str(raw['队伍']),
      teamPlacement: placement as TeamPlacement,
      honor: honor as HonorType,
      honorRank: num(raw['荣誉顺位']),
      rating: num(raw['Rating']),
      adr: num(raw['ADR']),
      kpr: num(raw['KPR']),
      maps: num(raw['地图数']) || undefined,
      vsTop5: optNum(raw['vsTop5']),
      vsTop10: optNum(raw['vsTop10']),
      vsTop20: optNum(raw['vsTop20']),
      vsTop30: optNum(raw['vsTop30']),
      vsTop50: optNum(raw['vsTop50']),
    };
  });
}

export interface ParsedData {
  players: Player[];
  events: Event[];
  results: EventResult[];
}

/** 把 ImportedRow 聚合为 Player/Event/EventResult 三张表 */
export function buildData(rows: ImportedRow[]): ParsedData {
  const players = new Map<string, Player>();
  const events = new Map<string, Event>();
  const results: EventResult[] = [];

  for (const r of rows) {
    const eventId = `${r.year}::${r.eventName}`;
    if (!events.has(eventId)) {
      events.set(eventId, {
        id: eventId,
        name: r.eventName,
        year: r.year,
        level: r.eventLevel,
        weight: r.eventWeight,
      });
    }
    const pid = `${r.year}::${r.playerId}`;
    if (!players.has(pid)) {
      players.set(pid, { id: pid, name: r.playerName, team: r.team, year: r.year });
    }
    results.push({
      eventId,
      playerId: pid,
      team: r.team || undefined,
      teamPlacement: r.teamPlacement,
      honor: r.honor,
      honorRank: r.honor === 'MVP' ? 1 : r.honor === 'EVP' ? r.honorRank : 0,
      rating: r.rating,
      adr: r.adr,
      kpr: r.kpr,
      maps: r.maps,
      vsTop5: r.vsTop5,
      vsTop10: r.vsTop10,
      vsTop20: r.vsTop20,
      vsTop30: r.vsTop30,
      vsTop50: r.vsTop50,
    });
  }
  return { players: [...players.values()], events: [...events.values()], results };
}

/** 从 File 读取并解析赛事数据 */
export async function importEventFile(file: File): Promise<ParsedData> {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf);
  const ws = wb.Sheets[wb.SheetNames[0]];
  const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(ws);
  if (raw.length === 0) throw new Error('Excel 中没有数据行');
  return buildData(parseRows(raw));
}

/**
 * 解析 HLTV 原版 Top20 sheet。
 * 两种格式均可：
 * - 两列：名次 / 选手名（单行一年，全部同一年）
 * - 三列：年份 / 名次 / 选手名
 */
export async function importBaselineFile(file: File, defaultYear?: number): Promise<HltvBaseline[]> {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf);
  const ws = wb.Sheets[wb.SheetNames[0]];
  const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(ws);
  if (raw.length === 0) throw new Error('Excel 中没有数据行');

  const byYear = new Map<number, HltvBaseline>();
  raw.forEach((r, i) => {
    const line = i + 2;
    const hasYearCol = raw[0] && '年份' in raw[0];
    const year = hasYearCol ? num(r['年份']) : defaultYear;
    if (!year) throw new Error(`第 ${line} 行：缺少年份，且未指定默认年份`);
    const rank = num(r['名次']);
    const name = str(r['选手名']);
    if (!rank || !name) throw new Error(`第 ${line} 行：名次或选手名为空`);
    if (!byYear.has(year)) byYear.set(year, { year, top20: [] });
    byYear.get(year)!.top20.push({ rank, playerName: name });
  });
  for (const b of byYear.values()) b.top20.sort((a, x) => a.rank - x.rank);
  return [...byYear.values()];
}

/** 赛事级别默认权重（供导入模板参考） */
export function defaultWeightOf(level: EventLevel): number {
  return DEFAULT_WEIGHTS.eventLevelWeights[level];
}
