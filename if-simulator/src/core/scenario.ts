import type { EventResult, IfScenario, Player, TeamPlacement } from '../types';
import { rankEvpCandidates } from './evp';

/**
 * 将 If 线方案应用到单个赛事的结果上，返回新的 EventResult 数组。
 * 规则：
 * - 冠军调整：新冠军队伍与原冠军队伍交换名次（按该赛事所在队伍判断，不受年内转会影响）
 * - MVP：newMvpId 获得 MVP；originalMvpAction 决定原 MVP 去向（「保持MVP」时新 MVP 不生效）
 * - EVP：手动 = 按 manualEvp 分配；
 *        自动 = 保留原 EVP 及其顺位，只处理被 MVP 变动挤掉或空出的位置。
 *        什么都没改时结果与原始数据完全一致。
 */
export function applyScenarioToEvent(
  eventResults: EventResult[],
  scenario: IfScenario,
  players: Player[],
): EventResult[] {
  const playerTeam = new Map(players.map((p) => [p.id, p.team]));
  // 优先用该赛事记录里的队伍；旧版本导入的数据没有，回退到选手的年度队伍
  const teamOf = (r: EventResult) => r.team || playerTeam.get(r.playerId) || '';
  let results = eventResults.map((r) => ({ ...r }));

  // 1. 冠军交换
  const champion = results.find((r) => r.teamPlacement === '冠军');
  const originalChampionTeam = champion ? teamOf(champion) : '';
  const newWinnerTeam = scenario.newWinnerTeam;
  if (newWinnerTeam && originalChampionTeam && newWinnerTeam !== originalChampionTeam) {
    const newWinnerOldPlacement = results.find((r) => teamOf(r) === newWinnerTeam)?.teamPlacement;
    const demoteTo: TeamPlacement = newWinnerOldPlacement ?? '亚军';
    results = results.map((r) => {
      const team = teamOf(r);
      if (team === newWinnerTeam) return { ...r, teamPlacement: '冠军' as TeamPlacement };
      if (team === originalChampionTeam) return { ...r, teamPlacement: demoteTo };
      return r;
    });
  }

  // 2. MVP 归属与原 MVP 去向
  const originalMvpId = eventResults.find((r) => r.honor === 'MVP')?.playerId ?? '';
  const newMvpId = scenario.newMvpId;
  const mvpId =
    newMvpId && newMvpId !== originalMvpId && scenario.originalMvpAction !== '保持MVP'
      ? newMvpId
      : originalMvpId;
  const mvpMoved = mvpId !== originalMvpId;
  const demotedId = mvpMoved && scenario.originalMvpAction === '降为EVP' ? originalMvpId : '';
  // 移除荣誉 / 转给他人：原 MVP 不再获得任何荣誉，也不能被自动补位补回来
  const removedId = mvpMoved && !demotedId ? originalMvpId : '';

  // 3. EVP 分配
  const evp =
    scenario.evpMode === '手动' && scenario.manualEvp
      ? manualEvp(scenario.manualEvp, mvpId, demotedId, scenario.originalMvpEvpRank)
      : autoEvp(results, eventResults, mvpId, demotedId, removedId, scenario.originalMvpEvpRank);

  return results.map((r): EventResult => {
    if (mvpId && r.playerId === mvpId) return { ...r, honor: 'MVP', honorRank: 1 };
    const rank = evp.get(r.playerId);
    if (rank) return { ...r, honor: 'EVP', honorRank: rank };
    return { ...r, honor: '无', honorRank: 0 };
  });
}

/**
 * 自动模式：保留原 EVP 及其顺位，只处理被挤掉或空出的位置。
 * - 新 MVP 原本是 EVP → 从 EVP 中移出，后面的人顺位前移
 * - 原 MVP 降为 EVP → 插到指定顺位；未指定时按 Rating/ADR 插入
 * - 超过 3 个 → 末位被挤掉；少于原 EVP 数 → 从淘汰赛选手中按 Rating/ADR 补足
 */
function autoEvp(
  results: EventResult[],
  original: EventResult[],
  mvpId: string,
  demotedId: string,
  removedId: string,
  demotedRank?: 1 | 2 | 3,
): Map<string, number> {
  const byId = new Map(results.map((r) => [r.playerId, r]));
  const originalEvp = original
    .filter((r) => r.honor === 'EVP')
    .sort((a, b) => a.honorRank - b.honorRank)
    .map((r) => r.playerId);
  const list = originalEvp.filter((id) => id !== mvpId && id !== demotedId && id !== removedId);

  if (demotedId) {
    let at = list.length;
    if (demotedRank) {
      at = Math.min(demotedRank - 1, list.length);
    } else {
      const me = byId.get(demotedId);
      const i = me
        ? list.findIndex((id) => {
            const o = byId.get(id);
            return !o || o.rating < me.rating || (o.rating === me.rating && o.adr < me.adr);
          })
        : -1;
      if (i >= 0) at = i;
    }
    list.splice(at, 0, demotedId);
  }

  // 空出的位置从淘汰赛选手中补足到原 EVP 数（原本就没有 EVP 的赛事不凭空生成）
  const want = Math.min(3, originalEvp.length);
  if (list.length < want) {
    const exclude = new Set([mvpId, removedId, ...list]);
    for (const r of rankEvpCandidates(results, exclude)) {
      if (list.length >= want) break;
      list.push(r.playerId);
    }
  }
  return new Map(list.slice(0, 3).map((id, i) => [id, i + 1]));
}

/** 手动模式：按指定顺位分配（同一顺位或同一人只取第一次）；原 MVP 降为 EVP 时放到指定或第一个空位 */
function manualEvp(
  manual: NonNullable<IfScenario['manualEvp']>,
  mvpId: string,
  demotedId: string,
  demotedRank?: 1 | 2 | 3,
): Map<string, number> {
  const out = new Map<string, number>();
  const used = new Set<number>();
  for (const e of manual) {
    if (!e.playerId || e.playerId === mvpId || out.has(e.playerId) || used.has(e.rank)) continue;
    out.set(e.playerId, e.rank);
    used.add(e.rank);
  }
  if (demotedId && !out.has(demotedId)) {
    const rank =
      demotedRank && !used.has(demotedRank) ? demotedRank : [1, 2, 3].find((k) => !used.has(k));
    if (rank) out.set(demotedId, rank);
  }
  return out;
}

/** 预览 If 线后的荣誉分配（供编辑页实时预览） */
export function previewHonors(
  eventResults: EventResult[],
  scenario: IfScenario,
  players: Player[],
): EventResult[] {
  return applyScenarioToEvent(eventResults, scenario, players);
}
