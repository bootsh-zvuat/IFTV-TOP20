import type { Event, EventResult, EventLevel, HltvBaseline, Player, TeamPlacement } from '../types';

/** 示例数据：2025 年，8 队 40 人，5 个赛事。仅用于演示与自测。 */

const YEAR = 2025;

const TEAMS: Record<string, [string, number][]> = {
  // 队伍: [选手名, 基准rating]
  Vitality: [['ZywOo', 1.35], ['ropz', 1.12], ['flameZ', 1.10], ['mezii', 1.05], ['apEX', 0.98]],
  Spirit: [['donk', 1.33], ['sh1ro', 1.18], ['zont1x', 1.02], ['magixx', 0.97], ['chopper', 0.92]],
  G2: [['m0NESY', 1.28], ['NiKo', 1.15], ['malbsMd', 1.05], ['huNter-', 1.00], ['Snax', 0.90]],
  Falcons: [['kyousuke', 1.14], ['TeSeS', 1.06], ['Magisk', 1.00], ['kyxsan', 0.95], ['SunPayus', 1.04]],
  MOUZ: [['torzsi', 1.12], ['xertioN', 1.08], ['Jimpphat', 1.04], ['Brollan', 1.03], ['Spinx', 1.06]],
  NAVI: [['w0nderful', 1.13], ['iM', 1.07], ['jL', 1.05], ['b1t', 1.10], ['Aleksib', 0.91]],
  FaZe: [['frozen', 1.12], ['broky', 1.08], ['rain', 1.02], ['EliGE', 1.06], ['karrigan', 0.88]],
  Aurora: [['XANTARES', 1.11], ['woxic', 1.06], ['MAJ3R', 0.99], ['Wicadia', 1.01], ['jottAAA', 0.96]],
};

interface EventDef {
  name: string;
  level: EventLevel;
  /** 按名次顺序列出队伍：冠军, 亚军, 四强, 四强, 八强, 八强, 八强, 八强 */
  order: string[];
}

const EVENT_DEFS: EventDef[] = [
  { name: 'IEM Katowice 2025', level: '超级精英赛', order: ['Vitality', 'Spirit', 'G2', 'MOUZ', 'NAVI', 'FaZe', 'Falcons', 'Aurora'] },
  { name: 'BLAST.tv Austin Major 2025', level: 'Major', order: ['Vitality', 'G2', 'Spirit', 'NAVI', 'MOUZ', 'Aurora', 'FaZe', 'Falcons'] },
  { name: 'IEM Cologne 2025', level: '大型赛事', order: ['Spirit', 'Vitality', 'MOUZ', 'G2', 'NAVI', 'FaZe', 'Aurora', 'Falcons'] },
  { name: 'BLAST Premier World Final 2025', level: '精英赛', order: ['G2', 'Vitality', 'Spirit', 'FaZe', 'MOUZ', 'NAVI', 'Falcons', 'Aurora'] },
  { name: 'StarLadder Budapest Major 2025', level: 'Major', order: ['Vitality', 'FaZe', 'Spirit', 'G2', 'MOUZ', 'NAVI', 'Falcons', 'Aurora'] },
];

const PLACEMENT_SEQ: TeamPlacement[] = ['冠军', '亚军', '四强', '四强', '八强', '八强', '八强', '八强'];

/** 确定性伪随机 */
function jitter(seed: number): number {
  const x = Math.sin(seed * 9973) * 10000;
  return (x - Math.floor(x) - 0.5) * 0.14;
}

export function samplePlayers(): Player[] {
  const players: Player[] = [];
  for (const [team, list] of Object.entries(TEAMS)) {
    for (const [name] of list) {
      players.push({ id: `${YEAR}::${name}`, name, team, year: YEAR });
    }
  }
  return players;
}

export function sampleEvents(): Event[] {
  return EVENT_DEFS.map((d) => ({
    id: `${YEAR}::${d.name}`,
    name: d.name,
    year: YEAR,
    level: d.level,
  }));
}

export function sampleResults(): EventResult[] {
  const results: EventResult[] = [];
  for (const [ei, def] of EVENT_DEFS.entries()) {
    const eventId = `${YEAR}::${def.name}`;
    const rows: { pid: string; team: string; placement: TeamPlacement; rating: number; adr: number }[] = [];
    def.order.forEach((team, ti) => {
      for (const [name, base] of TEAMS[team]) {
        const rating = Math.round((base + jitter(ei * 100 + ti * 10 + name.length)) * 100) / 100;
        rows.push({
          pid: `${YEAR}::${name}`,
          team,
          placement: PLACEMENT_SEQ[ti],
          rating,
          adr: Math.round((rating * 62 + jitter(ei + name.length)) * 10) / 10,
        });
      }
    });
    // MVP：冠军队内 rating 最高者
    const champRows = rows.filter((r) => r.placement === '冠军').sort((a, b) => b.rating - a.rating);
    const mvpId = champRows[0].pid;
    // EVP：淘汰赛选手中除 MVP 外 rating 前三
    const evpCandidates = rows
      .filter((r) => r.pid !== mvpId && ['冠军', '亚军', '四强', '八强'].includes(r.placement))
      .sort((a, b) => b.rating - a.rating || b.adr - a.adr);
    const evpMap = new Map<string, number>();
    evpCandidates.slice(0, 3).forEach((r, i) => evpMap.set(r.pid, i + 1));

    for (const r of rows) {
      const isMvp = r.pid === mvpId;
      const evpRank = evpMap.get(r.pid);
      results.push({
        eventId,
        playerId: r.pid,
        team: r.team,
        teamPlacement: r.placement,
        honor: isMvp ? 'MVP' : evpRank ? 'EVP' : '无',
        honorRank: isMvp ? 1 : evpRank ?? 0,
        rating: r.rating,
        adr: r.adr,
        kpr: Math.round(r.rating * 0.62 * 100) / 100,
      });
    }
  }
  return results;
}

/** 示例 HLTV 原版 Top20（演示基准，与算法结果略有出入以展示对比效果） */
export function sampleBaseline(): HltvBaseline {
  const names = [
    'ZywOo', 'donk', 'm0NESY', 'sh1ro', 'NiKo',
    'frozen', 'b1t', 'torzsi', 'w0nderful', 'kyousuke',
    'xertioN', 'ropz', 'flameZ', 'jL', 'broky',
    'XANTARES', 'iM', 'malbsMd', 'Spinx', 'Jimpphat',
  ];
  return {
    year: YEAR,
    top20: names.map((n, i) => ({ rank: i + 1, playerName: n, playerId: `${YEAR}::${n}` })),
  };
}

export const SAMPLE_YEAR = YEAR;
