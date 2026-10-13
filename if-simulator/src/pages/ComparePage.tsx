import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { db, loadWeights, yearData } from '../storage/db';
import { DEFAULT_WEIGHTS } from '../config/defaults';
import { computeRanking, top20 } from '../core/ranking';
import { applyScenarioToEvent } from '../core/scenario';
import type { HltvBaseline, IfScenario, RankingEntry } from '../types';

interface Row {
  playerId: string;
  name: string;
  team: string;
  score: number | null;
  simRank: number | null;
  baseRank: number | null;
}

export default function ComparePage() {
  const { year: yearStr } = useParams();
  const year = Number(yearStr);
  const [sp] = useSearchParams();
  const scenarioId = sp.get('scenario');

  const [baseline, setBaseline] = useState<HltvBaseline | null>(null);
  const [scenario, setScenario] = useState<IfScenario | null>(null);
  const [ranking, setRanking] = useState<RankingEntry[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      const cfg = await loadWeights(DEFAULT_WEIGHTS);
      const { events, results, players } = await yearData(year);
      let finalResults = results;
      let sc: IfScenario | null = null;
      if (scenarioId) {
        sc = (await db.scenarios.get(scenarioId)) ?? null;
        if (sc) {
          const modified = applyScenarioToEvent(
            results.filter((r) => r.eventId === sc!.eventId),
            sc,
            players,
          );
          finalResults = results.map((r) => {
            if (r.eventId !== sc!.eventId) return r;
            return modified.find((m) => m.playerId === r.playerId) ?? r;
          });
        }
      }
      setScenario(sc);
      setRanking(top20(computeRanking(year, events, finalResults, players, cfg)));
      setBaseline((await db.baselines.get(year)) ?? null);
      setLoaded(true);
    })();
  }, [year, scenarioId]);

  if (!loaded) return <p className="text-slate-400">加载中…</p>;

  // 基准匹配：优先 playerId，否则按名字（不区分大小写）
  const baseMap = new Map<string, number>();
  if (baseline) {
    for (const b of baseline.top20) {
      if (b.playerId) baseMap.set(`id:${b.playerId}`, b.rank);
      baseMap.set(`name:${b.playerName.toLowerCase()}`, b.rank);
    }
  }
  const findBaseRank = (e: RankingEntry): number | null =>
    baseMap.get(`id:${e.playerId}`) ?? baseMap.get(`name:${e.playerName.toLowerCase()}`) ?? null;

  const simRanks = new Map(ranking.map((e) => [e.playerId, e.rank]));
  const rows: Row[] = ranking.map((e) => ({
    playerId: e.playerId,
    name: e.playerName,
    team: e.team,
    score: e.totalScore,
    simRank: e.rank,
    baseRank: findBaseRank(e),
  }));
  // 基准中跌出榜单的选手
  const dropped: { name: string; baseRank: number }[] = baseline
    ? baseline.top20
        .filter((b) => {
          const pid = b.playerId;
          if (pid && simRanks.has(pid)) return false;
          return !ranking.some((e) => e.playerName.toLowerCase() === b.playerName.toLowerCase());
        })
        .map((b) => ({ name: b.playerName, baseRank: b.rank }))
    : [];

  const deltaBadge = (simRank: number, baseRank: number | null) => {
    if (baseRank === null)
      return <span className="rounded bg-blue-600/30 px-2 py-0.5 text-xs text-blue-300">新入榜</span>;
    const d = baseRank - simRank;
    if (d > 0) return <span className="rounded bg-emerald-600/30 px-2 py-0.5 text-xs text-emerald-300">↑{d}</span>;
    if (d < 0) return <span className="rounded bg-red-600/30 px-2 py-0.5 text-xs text-red-300">↓{-d}</span>;
    return <span className="rounded bg-slate-600/40 px-2 py-0.5 text-xs text-slate-300">—</span>;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">
          {year} Top20 对比{scenario ? ` — ${scenario.name}` : '（原始算法）'}
        </h2>
        <Link to={`/year/${year}`} className="text-sm text-blue-400 hover:underline">← 返回赛事列表</Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
          <h3 className="mb-2 font-semibold text-slate-300">HLTV 原版 Top20</h3>
          {!baseline ? (
            <p className="text-sm text-slate-400">未导入该年份 HLTV 基准。</p>
          ) : (
            <ol className="space-y-1 text-sm">
              {baseline.top20.map((b) => {
                const isDropped = dropped.some((d) => d.baseRank === b.rank);
                return (
                  <li key={b.rank} className="flex justify-between border-b border-slate-700/60 py-1">
                    <span>
                      <span className="mr-2 inline-block w-7 text-right text-slate-400">{b.rank}.</span>
                      {b.playerName}
                    </span>
                    {isDropped && scenario && (
                      <span className="rounded bg-red-600/30 px-2 py-0.5 text-xs text-red-300">跌出</span>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        <section className="rounded-lg border border-amber-700/50 bg-slate-800 p-4">
          <h3 className="mb-2 font-semibold text-amber-400">
            {scenario ? 'If 线模拟 Top20' : '原始算法 Top20'}
          </h3>
          <table className="w-full text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1 text-left">#</th>
                <th className="text-left">选手</th>
                <th className="text-left">队伍</th>
                <th className="text-right">总分</th>
                {baseline && <th className="text-right">名次变化</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.playerId} className="border-t border-slate-700/60">
                  <td className="py-1.5 text-slate-400">{r.simRank}</td>
                  <td>{r.name}</td>
                  <td className="text-slate-400">{r.team}</td>
                  <td className="text-right font-mono">{r.score?.toFixed(2)}</td>
                  {baseline && <td className="text-right">{deltaBadge(r.simRank!, r.baseRank)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
