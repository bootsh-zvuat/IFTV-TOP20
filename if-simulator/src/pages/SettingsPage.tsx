import { useEffect, useState } from 'react';
import { db, loadWeights, saveWeights } from '../storage/db';
import { DEFAULT_WEIGHTS, EVENT_LEVELS, TEAM_PLACEMENTS, WEIGHT_PRESETS } from '../config/defaults';
import type { WeightConfig } from '../types';

function NumInput({
  value,
  onChange,
  step = 0.05,
}: {
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <input
      type="number"
      step={step}
      value={value}
      onChange={(e) => {
        const v = Number(e.target.value);
        if (Number.isFinite(v)) onChange(v);
      }}
      className="w-24 rounded border border-slate-600 bg-slate-700 px-2 py-1 text-right text-sm"
    />
  );
}

export default function SettingsPage() {
  const [cfg, setCfg] = useState<WeightConfig>(DEFAULT_WEIGHTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadWeights(DEFAULT_WEIGHTS).then(setCfg);
  }, []);

  const update = (fn: (c: WeightConfig) => WeightConfig) => {
    setCfg((c) => fn(structuredClone(c)));
    setSaved(false);
  };

  const onSave = async () => {
    // 档位顺序不影响计算（取命中档的最高/最重分），保存时再按阈值排好，避免输入过程中整行跳动
    const sorted = { ...cfg, ratingTiers: [...cfg.ratingTiers].sort((a, b) => b.threshold - a.threshold) };
    setCfg(sorted);
    await saveWeights(sorted);
    setSaved(true);
  };

  const onReset = async () => {
    setCfg(structuredClone(DEFAULT_WEIGHTS));
    await saveWeights(structuredClone(DEFAULT_WEIGHTS));
    setSaved(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">权重设置</h2>
        <div className="flex gap-2">
          <button onClick={onReset} className="rounded bg-slate-600 px-4 py-2 text-sm hover:bg-slate-500">
            恢复默认
          </button>
          <button onClick={onSave} className="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500">
            保存
          </button>
        </div>
      </div>
      {saved && <p className="text-sm text-emerald-400">已保存。排名页将按新权重实时重算。</p>}

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-2 font-semibold">权重预设</h3>
        <div className="flex flex-wrap gap-2">
          {WEIGHT_PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                setCfg(structuredClone(p.weights));
                setSaved(false);
              }}
              title={p.note}
              className="rounded border border-slate-600 bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600"
            >
              {p.name}
              <span className="ml-2 text-xs text-slate-400">{p.note}</span>
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-400">
          「拟合校准」基于 2021-2025 历年 Top20 数据回归得出（留一年验证 Spearman 0.732 / MAE 2.97 名）：
          EVP 统一为 MVP 的一半、Major 与超级精英赛权重上调；
          名次分与 Rating 分档为 2025 真实数据经验校准。点击预设载入后需手动保存生效。
        </p>
        <p className="mt-2 text-xs text-amber-400/80">
          注意：拟合模型是「年度聚合 z-score」结构，与本模拟器的「逐赛事加和」结构不同，
          只有比例关系可移植。实测两套预设各有胜负：「拟合校准」前 6 名两年都更准
          （MAE 0.00 / 0.67，经验默认为 0.17 / 1.00），2024 年中段也更准（4.86 对 5.21）；
          2025 年中段则是「经验默认」更准（4.64 对 4.93）。
        </p>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-3 font-semibold">赛事级别权重</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EVENT_LEVELS.map((lv) => (
            <label key={lv} className="flex items-center justify-between text-sm">
              <span>{lv}</span>
              <NumInput
                value={cfg.eventLevelWeights[lv]}
                onChange={(v) => update((c) => ((c.eventLevelWeights[lv] = v), c))}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-3 font-semibold">队伍成绩调整</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {TEAM_PLACEMENTS.map((p) => (
            <label key={p} className="flex items-center justify-between text-sm">
              <span>{p}</span>
              <NumInput
                value={cfg.placementAdjust[p]}
                step={0.5}
                onChange={(v) => update((c) => ((c.placementAdjust[p] = v), c))}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-3 font-semibold">荣誉基础分</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(
            [
              ['MVP', 'MVP'],
              ['EVP1', '第一 EVP'],
              ['EVP2', '第二 EVP'],
              ['EVP3', '第三 EVP'],
              ['none', '无荣誉'],
              ['terrible', '表现极差'],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center justify-between text-sm">
              <span>{label}</span>
              <NumInput
                value={cfg.honorBase[key]}
                step={0.5}
                onChange={(v) => update((c) => ((c.honorBase[key] = v), c))}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-1 font-semibold">Rating 分档加分</h3>
        <p className="mb-3 text-xs text-slate-400">
          赛事 Rating 达到阈值即加对应分（取命中的最高档）；带「&lt;」的为负分档，低于阈值即扣分。保存时按阈值从高到低排列。
        </p>
        <div className="space-y-2">
          {cfg.ratingTiers.map((tier, i) => (
            <div key={i} className="flex items-center gap-3 text-sm">
              <span className="w-20 text-slate-400">第 {i + 1} 档</span>
              <label className="flex items-center gap-1">
                {tier.below ? 'Rating <' : 'Rating ≥'}
                <NumInput
                  value={tier.threshold}
                  step={0.05}
                  onChange={(v) => update((c) => ((c.ratingTiers[i].threshold = v), c))}
                />
              </label>
              <label className="flex items-center gap-1">
                加分
                <NumInput
                  value={tier.bonus}
                  step={0.5}
                  onChange={(v) => update((c) => ((c.ratingTiers[i].bonus = v), c))}
                />
              </label>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-3 font-semibold">参赛门槛与上下限</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="flex items-center justify-between text-sm">
            <span>最小年度图数</span>
            <NumInput value={cfg.minMaps} step={5} onChange={(v) => update((c) => ((c.minMaps = v), c))} />
          </label>
          <label className="flex items-center justify-between text-sm">
            <span>单赛事最小图数</span>
            <NumInput value={cfg.minEventMaps} step={1} onChange={(v) => update((c) => ((c.minEventMaps = v), c))} />
          </label>
          <label className="flex items-center justify-between text-sm">
            <span>表现分下限</span>
            <NumInput value={cfg.scoreMin} step={0.5} onChange={(v) => update((c) => ((c.scoreMin = v), c))} />
          </label>
          <label className="flex items-center justify-between text-sm">
            <span>表现分上限</span>
            <NumInput value={cfg.scoreMax} step={0.5} onChange={(v) => update((c) => ((c.scoreMax = v), c))} />
          </label>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          单赛事图数不足的出场记录不计分（防替补/教练蹭冠军分）；年度累计图数不足的选手不进榜（防低样本路人）。
          数据中没有图数信息时两项门槛均不启用。
        </p>
      </section>

      <section className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <h3 className="mb-3 font-semibold">HLTV 对手强度通道（v1.3.0）</h3>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex items-center justify-between text-sm">
            <span>通道权重</span>
            <NumInput
              value={cfg.opponentWeight}
              step={0.5}
              onChange={(v) => update((c) => ((c.opponentWeight = v), c))}
            />
          </label>
          <label className="flex items-center justify-between text-sm">
            <span>对手档位</span>
            <select
              className="rounded border border-slate-600 bg-slate-700 px-2 py-1 text-sm"
              value={cfg.opponentTier}
              onChange={(e) =>
                update((c) => ((c.opponentTier = Number(e.target.value) as 5 | 10 | 20 | 30 | 50), c))
              }
            >
              {[5, 10, 20, 30, 50].map((t) => (
                <option key={t} value={t}>
                  Top {t}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          用选手「对阵 Top-N 战队时的 Rating」（HLTV 口径）作为额外年度信号，
          做 z-score 归一化后加到总分。当前默认权重 0（关闭）、档位 Top 5。
        </p>
        <p className="mt-2 text-xs text-amber-400/80">
          <b>实验性功能</b>：该信号方向正确（中段 Spearman −0.385/−0.473，强于现行总分），
          但实测<b>无法稳定改善中段 MAE</b>（2025: 4.64↔4.50 非单调波动；
          Top20 重叠保持 18/20、17/20 无提升；权重 ≥5 后迅速恶化）。
          因此默认关闭。开启前请务必用真实数据回测。
        </p>
      </section>

      <p className="text-xs text-slate-500">
        说明：ADR 仅作为「自动重排 EVP」时 Rating 相同时的次要排序依据（见 core/evp.ts），
        不参与年度总分计算；KPR 当前不参与任何计算，仅为数据留存。
        权重保存在本地浏览器。
      </p>
    </div>
  );
}
