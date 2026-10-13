import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useLiveQuery } from 'dexie-react-hooks';
import { db, exportAll } from '../storage/db';

export default function SavesPage() {
  const scenarios = useLiveQuery(() => db.scenarios.orderBy('createdAt').reverse().toArray(), []) ?? [];
  const snapshots = useLiveQuery(() => db.snapshots.toArray(), []) ?? [];
  const events = useLiveQuery(() => db.events.toArray(), []) ?? [];
  const [msg, setMsg] = useState('');

  const eventName = (id: string) => events.find((e) => e.id === id)?.name ?? id;

  const onRename = async (id: string) => {
    const name = window.prompt('新的存档名称：');
    if (!name) return;
    const sc = await db.scenarios.get(id);
    if (sc) await db.scenarios.put({ ...sc, name });
  };

  const onDelete = async (id: string) => {
    if (!window.confirm('确定删除该 If 线存档及其排名快照？')) return;
    await db.scenarios.delete(id);
    await db.snapshots.where('scenarioId').equals(id).delete();
  };

  const onExport = async () => {
    const json = await exportAll();
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `if-simulator-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setMsg('已导出存档 JSON');
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">If 线存档管理</h2>
        <button onClick={onExport} className="rounded bg-slate-600 px-4 py-2 text-sm hover:bg-slate-500">
          导出全部存档 JSON
        </button>
      </div>
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}

      {scenarios.length === 0 ? (
        <p className="text-sm text-slate-400">暂无存档。请先在赛事列表中创建 If 线。</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800 text-slate-300">
              <tr>
                <th className="px-4 py-2 text-left">存档名称</th>
                <th className="px-4 py-2 text-left">年份</th>
                <th className="px-4 py-2 text-left">赛事</th>
                <th className="px-4 py-2 text-left">创建时间</th>
                <th className="px-4 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => {
                const snap = snapshots.find((x) => x.scenarioId === s.id);
                return (
                  <tr key={s.id} className="border-t border-slate-700 hover:bg-slate-800/60">
                    <td className="px-4 py-2">{s.name}</td>
                    <td className="px-4 py-2">{s.year}</td>
                    <td className="px-4 py-2">{eventName(s.eventId)}</td>
                    <td className="px-4 py-2 text-slate-400">
                      {new Date(s.createdAt).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex justify-end gap-3">
                        {snap && (
                          <Link
                            to={`/year/${s.year}/compare?scenario=${s.id}`}
                            className="text-amber-400 hover:underline"
                          >
                            查看对比
                          </Link>
                        )}
                        <button onClick={() => onRename(s.id)} className="text-blue-400 hover:underline">
                          重命名
                        </button>
                        <button onClick={() => onDelete(s.id)} className="text-red-400 hover:underline">
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
