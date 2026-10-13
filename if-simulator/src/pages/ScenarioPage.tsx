import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { db, loadWeights, yearData } from '../storage/db';
import { DEFAULT_WEIGHTS, ALGORITHM_VERSION } from '../config/defaults';
import { applyScenarioToEvent } from '../core/scenario';
import { computeRanking, top20 } from '../core/ranking';
import type {
  Event,
  EventResult,
  IfScenario,
  OriginalMvpAction,
  Player,
  RankingSnapshot,
} from '../types';

const ACTIONS: OriginalMvpAction[] = ['保持MVP', '降为EVP', '移除荣誉', '转给他人'];

export default function ScenarioPage() {
  const { year: yearStr, eventId: rawId } = useParams();
  const year = Number(yearStr);
  const eventId = decodeURIComponent(rawId ?? '');
  const navigate = useNavigate();

  const [event, setEvent] = useState<Event | null>(null);
  const [results, setResults] = useState<EventResult[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [loaded, setLoaded] = useState(false);

  // 表单状态
  const [newWinnerTeam, setNewWinnerTeam] = useState('');
  const [newMvpId, setNewMvpId] = useState('');
  const [action, setAction] = useState<OriginalMvpAction>('保持MVP');
  const [mvpEvpRank, setMvpEvpRank] = useState<'' | '1' | '2' | '3'>('');
  const [evpMode, setEvpMode] = useState<'自动' | '手动'>('自动');
  const [manualEvp, setManualEvp] = useState<('' | string)[]>(['', '', '']);
  const [scenarioName, setScenarioName] = useState('');

  useEffect(() => {
    (async () => {
      const ev = await db.events.get(eventId);
      const { results: all, players: ps } = await yearData(year);
      setEvent(ev ?? null);
      setResults(all.filter((r) => r.eventId === eventId));
      setPlayers(ps);
      setLoaded(true);
      if (ev) {
        const er = all.filter((r) => r.eventId === eventId);
        const pmap = new Map(ps.map((p) => [p.id, p]));
        const champ = er.find((r) => r.teamPlacement === '冠军');
        const mvp = er.find((r) => r.honor === 'MVP');
        if (champ) setNewWinnerTeam(pmap.get(champ.playerId)?.team ?? '');
        if (mvp) setNewMvpId(mvp.playerId);
        setScenarioName(`${ev.name} If线`);
      }
    })();
  }, [eventId, year]);

  const teams = useMemo(() => {
    const pmap = new Map(players.map((p) => [p.id, p]));
    return [...new Set(results.map((r) => pmap.get(r.playerId)?.team ?? ''))].filter(Boolean).sort();
  }, [players, results]);

  const playerName = (pid: string) => players.find((p) => p.id === pid)?.name ?? pid;

  const originalMvp = results.find((r) => r.honor === 'MVP');
  const originalEvps = results
    .filter((r) => r.honor === 'EVP')
    .sort((a, b) => a.honorRank - b.honorRank);
  const originalChampion = teams.find(
    (t) => players.find((p) => p.id === results.find((r) => r.teamPlacement === '冠军')?.playerId)?.team === t,
  );

  const scenario: IfScenario = useMemo(
    () => ({
      id: '',
      name: scenarioName,
      year,
      eventId,
      newWinnerTeam,
      newMvpId,
      originalMvpAction: action,
      originalMvpEvpRank: mvpEvpRank ? (Number(mvpEvpRank) as 1 | 2 | 3) : undefined,
      evpMode,
      manualEvp:
        evpMode === '手动'
          ? manualEvp
              .map((pid, i) => ({ playerId: pid, rank: (i + 1) as 1 | 2 | 3 }))
              .filter((e) => e.playerId)
          : undefined,
      createdAt: Date.now(),
    }),
    [scenarioName, year, eventId, newWinnerTeam, newMvpId, action, mvpEvpRank, evpMode, manualEvp],
  );

  const preview = useMemo(
    () => (loaded ? applyScenarioToEvent(results, scenario, players) : []),
    [loaded, results, scenario, players],
  );

  const previewMvp = preview.find((r) => r.honor === 'MVP');
  const previewEvps = preview.filter((r) => r.honor === 'EVP').sort((a, b) => a.honorRank - b.honorRank);

  const onRecalc = async () => {
    const cfg = await loadWeights(DEFAULT_WEIGHTS);
    const { events, results: all, players: ps } = await yearData(year);
    const modified = applyScenarioToEvent(
      all.filter((r) => r.eventId === eventId),
      scenario,
      ps,
    );
    const merged = all.map((r) => {
      if (r.eventId !== eventId) return r;
      return modified.find((m) => m.playerId === r.playerId) ?? r;
    });
    const ranking = top20(computeRanking(year, events, merged, ps, cfg));

    const sid = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const finalScenario: IfScenario = { ...scenario, id: sid, name: scenarioName || `${event?.name} If线` };
    await db.scenarios.put(finalScenario);
    const snapshot: RankingSnapshot = {
      id: `snap-${sid}`,
      year,
      scenarioId: sid,
      scenarioName: finalScenario.name,
      algorithmVersion: ALGORITHM_VERSION,
      createdAt: Date.now(),
      top20: ranking,
    };
    await db.snapshots.put(snapshot);
    navigate(`/year/${year}/compare?scenario=${sid}`);
  };

  if (!loaded) return <p className="text-slate-400">加载中…</p>;
  if (!event) return <p className="text-red-400">赛事不存在。</p>;

  const selCls = 'rounded border border-slate-600 bg-slate-700 px-2 py-1.5 text-sm';

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold">{event.name} — If 线编辑</h2>
        <p className="text-sm text-slate-400">{event.level} · {year}</p>
      </div>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-2 font-semibold">原始结果</h3>
        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div>冠军：<span className="text-amber-400">{originalChampion ?? '-'}</span></div>
          <div>MVP：<span className="text-amber-400">{originalMvp ? playerName(originalMvp.playerId) : '-'}</span></div>
          {originalEvps.map((r) => (
            <div key={r.playerId}>EVP{r.honorRank}：<span className="text-slate-200">{playerName(r.playerId)}</span></div>
          ))}
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="font-semibold">If 设定</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">新冠军队伍</span>
            <select value={newWinnerTeam} onChange={(e) => setNewWinnerTeam(e.target.value)} className={selCls + ' w-full'}>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">新 MVP</span>
            <select value={newMvpId} onChange={(e) => setNewMvpId(e.target.value)} className={selCls + ' w-full'}>
              {results.map((r) => (
                <option key={r.playerId} value={r.playerId}>{playerName(r.playerId)}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">原 MVP 处理方式</span>
            <select value={action} onChange={(e) => setAction(e.target.value as OriginalMvpAction)} className={selCls + ' w-full'}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          {action === '降为EVP' && (
            <label className="block text-sm">
              <span className="mb-1 block text-slate-300">原 MVP 的 EVP 顺位（可空=自动）</span>
              <select value={mvpEvpRank} onChange={(e) => setMvpEvpRank(e.target.value as typeof mvpEvpRank)} className={selCls + ' w-full'}>
                <option value="">自动</option>
                <option value="1">第一 EVP</option>
                <option value="2">第二 EVP</option>
                <option value="3">第三 EVP</option>
              </select>
            </label>
          )}
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">EVP 分配方式</span>
            <select value={evpMode} onChange={(e) => setEvpMode(e.target.value as '自动' | '手动')} className={selCls + ' w-full'}>
              <option value="自动">自动（按 Rating 重排淘汰赛选手）</option>
              <option value="手动">手动指定</option>
            </select>
          </label>
        </div>
        {evpMode === '手动' && (
          <div className="grid gap-3 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <label key={i} className="block text-sm">
                <span className="mb-1 block text-slate-300">第{'一二三'[i]} EVP</span>
                <select
                  value={manualEvp[i]}
                  onChange={(e) => setManualEvp((m) => m.map((v, j) => (j === i ? e.target.value : v)))}
                  className={selCls + ' w-full'}
                >
                  <option value="">（不指定）</option>
                  {results.filter((r) => r.playerId !== newMvpId).map((r) => (
                    <option key={r.playerId} value={r.playerId}>{playerName(r.playerId)}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        )}
        <label className="block text-sm sm:w-1/2">
          <span className="mb-1 block text-slate-300">存档名称</span>
          <input value={scenarioName} onChange={(e) => setScenarioName(e.target.value)} className={selCls + ' w-full'} />
        </label>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-2 font-semibold">改动预览</h3>
        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div>冠军：<span className="text-emerald-400">{newWinnerTeam}</span></div>
          <div>MVP：<span className="text-emerald-400">{previewMvp ? playerName(previewMvp.playerId) : '-'}</span></div>
          {previewEvps.map((r) => (
            <div key={r.playerId}>EVP{r.honorRank}：<span className="text-slate-200">{playerName(r.playerId)}</span></div>
          ))}
        </div>
      </section>

      <button onClick={onRecalc} className="rounded bg-amber-600 px-6 py-2.5 font-semibold hover:bg-amber-500">
        重算全年 Top20 并保存存档
      </button>
    </div>
  );
}
