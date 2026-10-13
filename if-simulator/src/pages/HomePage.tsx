import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useLiveQuery } from 'dexie-react-hooks';
import { db, importAll, listYears, replaceYearData } from '../storage/db';
import { importBaselineFile, importEventFile } from '../core/excel';
import { sampleBaseline, sampleEvents, samplePlayers, sampleResults, SAMPLE_YEAR } from '../data/sample';

export default function HomePage() {
  const navigate = useNavigate();
  const years = useLiveQuery(() => listYears(), []) ?? [];
  const baselines = useLiveQuery(() => db.baselines.toArray(), []) ?? [];
  const [msg, setMsg] = useState('');
  const [baselineYear, setBaselineYear] = useState('');
  const eventFileRef = useRef<HTMLInputElement>(null);
  const baselineFileRef = useRef<HTMLInputElement>(null);
  const importFileRef = useRef<HTMLInputElement>(null);

  const onImportEvents = async (f: File) => {
    try {
      const data = await importEventFile(f);
      const years = [...new Set(data.events.map((e) => e.year))];
      await replaceYearData(years, data.players, data.events, data.results);
      setMsg(`导入成功：${data.events.length} 个赛事、${data.players.length} 名选手、${data.results.length} 条记录`);
    } catch (e) {
      setMsg(`导入失败：${(e as Error).message}`);
    }
  };

  const onImportBaseline = async (f: File) => {
    try {
      const list = await importBaselineFile(f, baselineYear ? Number(baselineYear) : undefined);
      await db.baselines.bulkPut(list);
      setMsg(`HLTV 基准导入成功：${list.map((b) => `${b.year}(${b.top20.length}人)`).join('、')}`);
    } catch (e) {
      setMsg(`基准导入失败：${(e as Error).message}`);
    }
  };

  const onLoadSample = async () => {
    await replaceYearData([SAMPLE_YEAR], samplePlayers(), sampleEvents(), sampleResults());
    await db.baselines.put(sampleBaseline());
    setMsg('示例数据已加载（2025 年，40 名选手、5 个赛事）');
  };

  const onImportAll = async (f: File) => {
    try {
      await importAll(await f.text());
      setMsg('存档 JSON 导入成功');
    } catch (e) {
      setMsg(`存档导入失败：${(e as Error).message}`);
    }
  };

  const pick = (ref: React.RefObject<HTMLInputElement>, cb: (f: File) => void) => ({
    onClick: () => ref.current?.click(),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) cb(f);
      e.target.value = '';
    },
  });
  const ev = pick(eventFileRef, onImportEvents);
  const bl = pick(baselineFileRef, onImportBaseline);
  const ia = pick(importFileRef, onImportAll);

  return (
    <div className="space-y-8">
      <section className="rounded-lg border border-slate-700 bg-slate-800 p-5">
        <h2 className="mb-3 text-lg font-semibold">数据导入</h2>
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={ev.onClick} className="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500">
            导入赛事数据 Excel
          </button>
          <input ref={eventFileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={ev.onChange} />

          <input
            value={baselineYear}
            onChange={(e) => setBaselineYear(e.target.value)}
            placeholder="基准年份(可选)"
            className="w-32 rounded border border-slate-600 bg-slate-700 px-2 py-2 text-sm"
          />
          <button onClick={bl.onClick} className="rounded bg-emerald-600 px-4 py-2 text-sm hover:bg-emerald-500">
            导入 HLTV 原版 Top20
          </button>
          <input ref={baselineFileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={bl.onChange} />

          <button onClick={onLoadSample} className="rounded bg-amber-600 px-4 py-2 text-sm hover:bg-amber-500">
            加载示例数据
          </button>
          <button onClick={ia.onClick} className="rounded bg-slate-600 px-4 py-2 text-sm hover:bg-slate-500">
            导入存档 JSON
          </button>
          <input ref={importFileRef} type="file" accept=".json" className="hidden" onChange={ia.onChange} />
        </div>
        {msg && <p className="mt-3 text-sm text-slate-300">{msg}</p>}
        <p className="mt-3 text-xs text-slate-400">
          Excel 列：年份 / 赛事名称 / 赛事级别 / 赛事权重(可空) / 选手ID / 选手名 / 队伍 / 队伍名次 / 荣誉类型 / 荣誉顺位 / Rating / ADR / KPR。
          可选列：地图数、vsTop5 / vsTop10 / vsTop20 / vsTop30 / vsTop50（HLTV 对手强度，缺省不影响计算）。
          基准文件列：名次 / 选手名（或含年份列）。
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">选择年份</h2>
        {years.length === 0 ? (
          <p className="text-sm text-slate-400">暂无数据，请先导入 Excel 或加载示例数据。</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {years.map((y) => {
              const hasBaseline = baselines.some((b) => b.year === y);
              return (
                <button
                  key={y}
                  onClick={() => navigate(`/year/${y}`)}
                  className="rounded-lg border border-slate-700 bg-slate-800 p-6 text-center hover:border-amber-500"
                >
                  <div className="text-2xl font-bold">{y}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    {hasBaseline ? '含 HLTV 基准' : '无 HLTV 基准'}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">快捷入口</h2>
        <div className="flex gap-3 text-sm">
          <Link to="/saves" className="text-blue-400 hover:underline">If 线存档管理 →</Link>
          <Link to="/settings" className="text-blue-400 hover:underline">权重设置 →</Link>
        </div>
      </section>
    </div>
  );
}
