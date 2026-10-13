import { readFileSync } from 'node:fs';
import { DEFAULT_WEIGHTS, FITTED_WEIGHTS } from '../src/config/defaults';
import { computeRanking } from '../src/core/ranking';
import type { Event, EventResult, Player, WeightConfig } from '../src/types';

interface BaselineEntry { rank: number; playerId: string; name: string }
interface VerifyData {
  players: Player[];
  events: Event[];
  results: EventResult[];
  baselines: Record<string, BaselineEntry[]>;
}

const data: VerifyData = JSON.parse(
  readFileSync(new URL('./verify-data.json', import.meta.url), 'utf-8'),
);

function spearman(a: number[], b: number[]): number {
  const n = a.length;
  const d2 = a.reduce((s, x, i) => s + (x - b[i]) ** 2, 0);
  return 1 - (6 * d2) / (n * (n * n - 1));
}

function evaluate(year: number, cfg: WeightConfig, label: string) {
  const entries = computeRanking(year, data.events, data.results, data.players, cfg);
  const baseline = data.baselines[String(year)] ?? [];
  const rankOf = new Map(entries.map((e) => [e.playerId, e.rank]));
  const fallback = entries.length + 1;

  const officials = baseline.map((b) => b.rank);
  const preds = baseline.map((b) => rankOf.get(b.playerId) ?? fallback);
  const sp = spearman(officials, preds);
  const mae = preds.reduce((s, p, i) => s + Math.abs(p - officials[i]), 0) / preds.length;
  const predTop20 = new Set(entries.slice(0, 20).map((e) => e.playerId));
  const predTop5 = new Set(entries.slice(0, 5).map((e) => e.playerId));
  const overlap20 = baseline.filter((b) => predTop20.has(b.playerId)).length;
  const overlap5 = baseline.filter((b) => b.rank <= 5 && predTop5.has(b.playerId)).length;
  const missing = baseline.filter((b) => !rankOf.has(b.playerId)).map((b) => b.name);

  console.log(`\n[${year}] ${label}: Spearman=${sp.toFixed(3)}  MAE=${mae.toFixed(2)}  Top20重叠=${overlap20}/20  Top5重叠=${overlap5}/5`);
  if (missing.length) console.log(`  无数据官方选手: ${missing.join(', ')}`);
  console.log('  名次对照(官方→预测): ' + baseline.map((b, i) => `${b.name} ${b.rank}→${preds[i]}`).join(' | '));
  console.log('  预测Top10: ' + entries.slice(0, 10).map((e) => `${e.rank}.${e.playerName}(${e.totalScore})`).join(' '));
  return { sp, mae, overlap20, overlap5 };
}

for (const year of [2024, 2025]) {
  evaluate(year, DEFAULT_WEIGHTS, '经验默认');
  evaluate(year, FITTED_WEIGHTS, '拟合校准');
}
