import type { EventResult, IfScenario, Player, TeamPlacement } from '../types';
import { autoAssignEvp } from './evp';

const NO_HONOR = (r: EventResult): EventResult => ({ ...r, honor: '无', honorRank: 0 });

/**
 * 将 If 线方案应用到单个赛事的结果上，返回新的 EventResult 数组。
 * 规则：
 * - 冠军调整：新冠军队伍与原冠军队伍交换名次
 * - MVP：newMvpId 获得 MVP；originalMvpAction 决定原 MVP 去向
 * - EVP：手动 = 按 manualEvp 分配；自动 = 排除 MVP 后按 Rating/ADR 对淘汰赛选手重排
 */
export function applyScenarioToEvent(
  eventResults: EventResult[],
  scenario: IfScenario,
  players: Player[],
): EventResult[] {
  const playerTeam = new Map(players.map((p) => [p.id, p.team]));
  let results = eventResults.map((r) => ({ ...r }));

  // 1. 冠军交换
  const originalChampionTeam = playerTeam.get(
    results.find((r) => r.teamPlacement === '冠军')?.playerId ?? '',
  );
  const newWinnerTeam = scenario.newWinnerTeam;
  if (newWinnerTeam && originalChampionTeam && newWinnerTeam !== originalChampionTeam) {
    const newWinnerOldPlacement = results.find(
      (r) => playerTeam.get(r.playerId) === newWinnerTeam,
    )?.teamPlacement;
    const demoteTo: TeamPlacement = newWinnerOldPlacement ?? '亚军';
    results = results.map((r) => {
      const team = playerTeam.get(r.playerId);
      if (team === newWinnerTeam) return { ...r, teamPlacement: '冠军' as TeamPlacement };
      if (team === originalChampionTeam) return { ...r, teamPlacement: demoteTo };
      return r;
    });
  }

  // 2. 清空荣誉
  results = results.map(NO_HONOR);

  const originalMvpId = eventResults.find((r) => r.honor === 'MVP')?.playerId ?? '';
  const newMvpId = scenario.newMvpId;

  // 3. MVP 归属
  const setHonor = (playerId: string, honor: 'MVP' | 'EVP', rank: number) => {
    results = results.map((r) =>
      r.playerId === playerId ? { ...r, honor, honorRank: rank } : r,
    );
  };
  const mvpChanged = newMvpId && newMvpId !== originalMvpId;
  if (mvpChanged) {
    setHonor(newMvpId, 'MVP', 1);
  } else if (originalMvpId) {
    setHonor(originalMvpId, 'MVP', 1);
  }

  // 4. 原 MVP 处理（仅在 MVP 易主时有意义）
  let reservedEvpRank: number | null = null;
  if (mvpChanged && originalMvpId) {
    if (scenario.originalMvpAction === '降为EVP') {
      const rank = scenario.originalMvpEvpRank ?? null;
      if (rank) {
        setHonor(originalMvpId, 'EVP', rank);
        reservedEvpRank = rank;
      }
      // 未指定顺位时由自动重排插入
    } else if (scenario.originalMvpAction === '移除荣誉' || scenario.originalMvpAction === '转给他人') {
      // 已清空，无需处理
    } else if (scenario.originalMvpAction === '保持MVP') {
      // 保持原 MVP：撤销新 MVP
      setHonor(originalMvpId, 'MVP', 1);
      results = results.map((r) =>
        r.playerId === newMvpId ? { ...r, honor: '无', honorRank: 0 } : r,
      );
    }
  }
  const effectiveMvpId =
    mvpChanged && scenario.originalMvpAction !== '保持MVP' ? newMvpId : originalMvpId;

  // 5. EVP 分配
  if (scenario.evpMode === '手动' && scenario.manualEvp) {
    for (const e of scenario.manualEvp) {
      if (e.playerId && e.playerId !== effectiveMvpId) setHonor(e.playerId, 'EVP', e.rank);
    }
  } else {
    const auto = autoAssignEvp(results, effectiveMvpId || null);
    // 原 MVP 降为 EVP 且指定了顺位：保留该顺位，其余自动填充
    if (reservedEvpRank) auto.delete(originalMvpId);
    const usedRanks = new Set<number>(reservedEvpRank ? [reservedEvpRank] : []);
    for (const [pid, rank] of auto) {
      let r = rank;
      while (usedRanks.has(r) && r < 3) r++;
      if (usedRanks.has(r)) continue;
      usedRanks.add(r);
      setHonor(pid, 'EVP', r);
    }
    if (reservedEvpRank) setHonor(originalMvpId, 'EVP', reservedEvpRank);
  }

  return results;
}

/** 预览 If 线后的荣誉分配（供编辑页实时预览） */
export function previewHonors(
  eventResults: EventResult[],
  scenario: IfScenario,
  players: Player[],
): EventResult[] {
  return applyScenarioToEvent(eventResults, scenario, players);
}
