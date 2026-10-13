// apEX 分数构成解剖：为什么指挥能进 Top20
import { readFileSync } from 'node:fs';
import * as XLSX from 'xlsx';
import { parseRows, buildData } from '../src/core/excel';
import { eventPerformanceScore, ratingTierBonus } from '../src/core/score';
import { eventWeight } from '../src/core/ranking';
import { DEFAULT_WEIGHTS } from '../src/config/defaults';

const wb = XLSX.read(readFileSync(new URL('../../data/if_sim_2025_events.xlsx', import.meta.url)));
const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(wb.Sheets[wb.SheetNames[0]]);
const data = buildData(parseRows(raw));

const evMap = new Map(data.events.map((e) => [e.id, e]));
const mine = data.results.filter((r) => {
  const p = data.players.find((x) => x.id === r.playerId);
  return p?.name === 'apEX' || p?.name === 'flameZ' || p?.name === 'frozen';
});

for (const name of ['apEX', 'flameZ', 'frozen']) {
  const rs = mine.filter((r) => data.players.find((x) => x.id === r.playerId)?.name === name);
  let total = 0;
  console.log(`\n=== ${name}（${rs.length} 赛事）===`);
  const byPlace: Record<string, number> = {};
  for (const r of rs.sort((a, b) => (evMap.get(a.eventId)?.name ?? '').localeCompare(evMap.get(b.eventId)?.name ?? ''))) {
    const ev = evMap.get(r.eventId)!;
    const w = eventWeight(ev, DEFAULT_WEIGHTS);
    const s = eventPerformanceScore(r, DEFAULT_WEIGHTS);
    total += s * w;
    byPlace[r.teamPlacement] = (byPlace[r.teamPlacement] ?? 0) + 1;
    console.log(
      `  ${ev.name.slice(0, 34).padEnd(36)} w=${w.toFixed(2)} rating=${r.rating.toFixed(2)}(+${ratingTierBonus(r.rating, DEFAULT_WEIGHTS)}) ${r.honor} ${r.teamPlacement} → ${s.toFixed(1)}×${w.toFixed(2)}=${(s * w).toFixed(2)}`,
    );
  }
  console.log(`  名次分布: ${JSON.stringify(byPlace)}  总分 ${total.toFixed(2)}`);
}
