import { Link, useParams } from 'react-router-dom';
import { useLiveQuery } from 'dexie-react-hooks';
import { db, loadWeights } from '../storage/db';
import { DEFAULT_WEIGHTS } from '../config/defaults';
import { eventWeight } from '../core/ranking';
import { useEffect, useState } from 'react';
import type { WeightConfig } from '../types';

export default function EventsPage() {
  const { year: yearStr } = useParams();
  const year = Number(yearStr);
  const events = useLiveQuery(
    () => db.events.where('year').equals(year).toArray(),
    [year],
  );
  const [cfg, setCfg] = useState<WeightConfig>(DEFAULT_WEIGHTS);
  useEffect(() => {
    loadWeights(DEFAULT_WEIGHTS).then(setCfg);
  }, []);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold">{year} 年赛事列表</h2>
        <Link to={`/year/${year}/compare`} className="rounded bg-emerald-600 px-4 py-2 text-sm hover:bg-emerald-500">
          查看原始算法 Top20 对比
        </Link>
      </div>
      {!events ? (
        <p className="text-slate-400">加载中…</p>
      ) : events.length === 0 ? (
        <p className="text-slate-400">该年份暂无赛事数据。</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800 text-slate-300">
              <tr>
                <th className="px-4 py-2 text-left">赛事名称</th>
                <th className="px-4 py-2 text-left">级别</th>
                <th className="px-4 py-2 text-right">权重</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-slate-700 hover:bg-slate-800/60">
                  <td className="px-4 py-2">{e.name}</td>
                  <td className="px-4 py-2">
                    <span className="rounded bg-slate-700 px-2 py-0.5 text-xs">{e.level}</span>
                  </td>
                  <td className="px-4 py-2 text-right">{eventWeight(e, cfg).toFixed(2)}</td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      to={`/year/${year}/event/${encodeURIComponent(e.id)}`}
                      className="text-amber-400 hover:underline"
                    >
                      创建 If 线 →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
