// 用模拟器真实代码（excel.ts/ranking.ts/defaults.ts）离线验证 2025 真实数据导入
// 运行：npx esbuild scripts/import-check.ts --bundle --platform=node --format=esm --outfile=scripts/import-check.mjs && node scripts/import-check.mjs
import { readFileSync } from 'node:fs';
import * as XLSX from 'xlsx';
import { parseRows, buildData } from '../src/core/excel';
import { computeRanking } from '../src/core/ranking';
import { DEFAULT_WEIGHTS, FITTED_WEIGHTS, type WeightConfig } from '../src/config/defaults';

const BASE = new URL('../../data/', import.meta.url);

function loadXlsx(name: string): Record<string, unknown>[] {
  const wb = XLSX.read(readFileSync(new URL(name, BASE)));
  const ws = wb.Sheets[wb.SheetNames[0]];
  return XLSX.utils.sheet_to_json<Record<string, unknown>>(ws);
}

// 1. 解析校验（与 importEventFile 同一代码路径）
const rawEvents = loadXlsx('if_sim_2025_events.xlsx');
const rows = parseRows(rawEvents);
const data = buildData(rows);
console.log(`赛事数据解析 OK：${rows.length} 行 → ${data.events.length} 赛事 / ${data.players.length} 选手 / ${data.results.length} 结果`);

// 2. 基准（与 importBaselineFile 同逻辑：有「年份」列）
const rawBase = loadXlsx('if_sim_2025_baseline.xlsx');
const baseline = rawBase
  .map((r) => ({ year: Number(r['年份']), rank: Number(r['名次']), name: String(r['选手名']).trim() }))
  .sort((a, b) => a.rank - b.rank);
console.log(`基准解析 OK：${baseline.length} 人，top1=${baseline[0].name}`);

function spearman(a: number[], b: number[]): number {
  const n = a.length;
  const d2 = a.reduce((s, x, i) => s + (x - b[i]) ** 2, 0);
  return 1 - (6 * d2) / (n * (n * n - 1));
}

// 3. 两套预设计算排名并与官方基准按名字对比
function evaluate(cfg: WeightConfig, label: string) {
  const entries = computeRanking(2025, data.events, data.results, data.players, cfg);
  const byName = new Map(entries.map((e) => [e.playerName, e.rank]));
  const lines = baseline.map((b) => `${b.rank}.${b.name}→${byName.get(b.name) ?? '榜外'}`);
  const fallback = entries.length + 1;
  const preds = baseline.map((b) => byName.get(b.name) ?? fallback);
  const sp = spearman(baseline.map((b) => b.rank), preds);
  const mae = preds.reduce((s, p, i) => s + Math.abs(p - baseline[i].rank), 0) / preds.length;
  const top20set = new Set(entries.slice(0, 20).map((e) => e.playerName));
  const overlap = baseline.filter((b) => top20set.has(b.name)).length;
  console.log(`\n[${label}] 上榜 ${entries.length} 人 | Spearman=${sp.toFixed(3)} MAE=${mae.toFixed(1)} Top20重叠=${overlap}/20`);
  console.log(`[${label}] 预测Top20: ${entries.slice(0, 20).map((e) => `${e.rank}.${e.playerName}`).join(' ')}`);
  console.log(`[${label}] 官方→预测: ${lines.join(' | ')}`);
}
evaluate(DEFAULT_WEIGHTS, '经验默认');
evaluate(FITTED_WEIGHTS, '拟合校准');
