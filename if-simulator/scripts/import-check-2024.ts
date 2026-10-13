import { readFileSync } from 'node:fs';
import * as XLSX from 'xlsx';
import { parseRows, buildData } from '../src/core/excel';
import { computeRanking } from '../src/core/ranking';
import { DEFAULT_WEIGHTS, FITTED_WEIGHTS } from '../src/config/defaults';

const BASE = new URL('../../data/', import.meta.url);
function loadXlsx(name: string): Record<string, unknown>[] {
  const wb = XLSX.read(readFileSync(new URL(name, BASE)));
  return XLSX.utils.sheet_to_json<Record<string, unknown>>(wb.Sheets[wb.SheetNames[0]]);
}

for (const year of [2024]) {
  const rawEvents = loadXlsx(`if_sim_${year}_events.xlsx`);
  const data = buildData(parseRows(rawEvents));
  console.log(`\n[${year}] 赛事数据：${data.events.length} 赛事 / ${data.players.length} 选手 / ${data.results.length} 结果`);

  const rawBase = loadXlsx(`if_sim_${year}_baseline.xlsx`);
  const baseline = rawBase
    .map((r) => ({ rank: Number(r['名次']), name: String(r['选手名']).trim() }))
    .sort((a, b) => a.rank - b.rank);

  for (const [label, cfg] of [['经验默认', DEFAULT_WEIGHTS], ['拟合校准', FITTED_WEIGHTS]] as const) {
    const entries = computeRanking(year, data.events, data.results, data.players, cfg);
    const byName = new Map(entries.map((e) => [e.playerName, e.rank]));
    const lines = baseline.map((b) => `${b.rank}.${b.name}→${byName.get(b.name) ?? '榜外'}`);
    const overlaps = baseline.filter((b) => byName.has(b.name));
    const sp = baseline.filter((b) => byName.has(b.name)).length;
    console.log(`[${label}] 预测Top20: ${entries.slice(0, 20).map((e) => `${e.rank}.${e.playerName}`).join(' ')}`);
    console.log(`[${label}] 官方→预测: ${lines.join(' | ')}`);
    console.log(`[${label}] Top20 重叠 ${sp}/20，官方在榜内: ${overlaps.map((b) => b.name).join(', ')}`);
    console.log(`[${label}] 官方榜外人: ${baseline.filter((b) => !byName.has(b.name)).map((b) => b.name).join(', ')}`);
  }
}
