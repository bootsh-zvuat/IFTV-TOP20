# -*- coding: utf-8 -*-
"""
CS2 选手排名数据采集器
数据源：
  1. 完美世界电竞数据 data.wanmei.com（HLTV 口径，含 vs Top5/10/20/30/50 拆分、荣誉、历年 Top20、MVP）
  2. 5EPlay event.5eplay.com（自定义时间段 + 赛事等级的多维度榜单）
输出：data/CS2选手排名数据_<时间戳>.xlsx（多工作表）

运行：.venv\\Scripts\\python.exe crawler.py
"""
import os
import sys
import time
import hmac
import json
import math
import errno
import random
import hashlib
import secrets
import datetime
import urllib.parse
from collections import OrderedDict

# ---------- 依赖自检 ----------
try:
    import requests
except ImportError:
    print("缺少依赖 requests，请先执行：.venv\\Scripts\\python.exe -m pip install requests openpyxl")
    sys.exit(1)
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    print("缺少依赖 openpyxl，请先执行：.venv\\Scripts\\python.exe -m pip install requests openpyxl")
    sys.exit(1)

# ---------- 全局配置 ----------
TOP_N = 100                # 采集选手榜前 N 名（详情接口按人调用，N 越大耗时越长）
WMPAGE_SIZE = 100          # 完美榜单每页数量
SLEEP_WM = 0.35            # 完美接口请求间隔（秒），限速保护
SLEEP_5E = 0.3             # 5E 接口请求间隔（秒）
YEAR_START = f"{datetime.date.today().year}-01-01 00:00:00"
YEAR_END = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# 赛事等级：1=Major 7=S+ 2=S 3=A 9=资格赛A级
GRADES = ["1", "7", "2", "3", "9"]
# 历史采集：Top20 选手的逐赛事荣誉 + 逐年统计（拟合用）
HIST_YEAR_START = 2013
HIST_YEAR_END = datetime.date.today().year

WM_BASE = "https://esports.wanmei.com/apg/eventcenter/csgo"
WM_SECRET = b"828a59393861babc4a27e23f87fc77ab8dc9347dc6550c5e7e51e9b1af2de812"
E5_BASE = "https://esports-data.5eplaycdn.com/v1/api/csgo"

HEADERS_WM = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://data.wanmei.com/",
    "platform": "pc_web",
}
HEADERS_5E = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Content-Type": "application/json",
    "Origin": "https://event.5eplay.com",
    "Referer": "https://event.5eplay.com/",
}

session = requests.Session()


# ---------- 工具函数 ----------
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def request_get(url, params=None, headers=None, retries=2, timeout=30):
    last_err = None
    for _ in range(retries + 1):
        try:
            return session.get(url, params=params or {}, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0)
    raise last_err


def request_post(url, payload, headers=None, retries=2, timeout=30):
    last_err = None
    for _ in range(retries + 1):
        try:
            return session.post(url, data=json.dumps(payload), headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            time.sleep(1.0)
    raise last_err


def rfc3986(s):
    return urllib.parse.quote(str(s), safe="-._~")


def ms_to_date(v):
    try:
        v = float(v)
        if v > 1e11:  # 毫秒时间戳
            return datetime.datetime.fromtimestamp(v / 1000).strftime("%Y-%m-%d")
        if v > 1e9:
            return datetime.datetime.fromtimestamp(v).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    return ""


def flatten(obj, prefix="", out=None, skip_keys=None):
    """把嵌套 dict/list 扁平化为 {a.b: 标量}，跳过指定键的大块内容。"""
    if out is None:
        out = OrderedDict()
    if skip_keys is None:
        skip_keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip_keys:
                continue
            key = f"{prefix}.{k}" if prefix else str(k)
            flatten(v, key, out, skip_keys)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}[{i}]", out, skip_keys)
    else:
        out[prefix] = obj
    return out


# ---------- 完美世界客户端（HMAC-SHA256 签名） ----------
def wm_get(path, params=None):
    params = dict(params or {})
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    pairs = sorted([(k, str(v)) for k, v in params.items()] +
                   [("timestamp", ts), ("nonce", nonce)])
    canonical = "&".join(f"{rfc3986(k)}={rfc3986(v)}" for k, v in pairs)
    sig = hmac.new(WM_SECRET, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = dict(HEADERS_WM)
    headers.update({"X-Timestamp": ts, "X-Nonce": nonce, "X-Signature": sig})
    resp = request_get(WM_BASE + path, params, headers)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"完美接口 {path} 返回异常: {data.get('code')} {data.get('message')}")
    return data.get("result")


def fetch_wm_leaderboard():
    """选手总榜（当年），返回前 TOP_N 行。"""
    log(f"完美：拉取选手总榜前 {TOP_N} 名 ...")
    rows = []
    page = 1
    while len(rows) < TOP_N:
        batch = wm_get("/player/stats", {"pageNum": page, "pageSize": WMPAGE_SIZE, "darkType": 1})
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < WMPAGE_SIZE:
            break
        page += 1
        time.sleep(SLEEP_WM)
    return rows[:TOP_N]


def fetch_wm_detail(player_id):
    time.sleep(SLEEP_WM)
    return wm_get("/player/stat/detail", {"playerId": player_id})


def fetch_wm_top20():
    log("完美：拉取历年 HLTV Top20 入选记录 ...")
    return wm_get("/player/top20") or {}


def fetch_wm_mvp():
    log("完美：拉取历年 MVP 统计 ...")
    return wm_get("/player/mvp") or {}


def fetch_wm_latest_honor():
    log("完美：拉取近期赛事荣誉 ...")
    return wm_get("/player/latest/honor") or {}


def fetch_wm_career(player_id):
    """选手生涯荣誉（逐赛事，按年份分组）。type: 1=MVP 2=年度Top20 4=队伍名次 5=EVP"""
    time.sleep(SLEEP_WM)
    return wm_get("/player/career", {"playerId": player_id}) or []


# ---------- 5EPlay 客户端（POST JSON，无鉴权） ----------
def e5_multidimension_page(page):
    body = {
        "dimension": "",
        "sort_key": "rating",
        "sort_value": "DESC",
        "player_options": {
            "tt_ids": [],
            "time_value": f"{YEAR_START}_{YEAR_END}",
            "grade": GRADES,
            "player_id": "",
            "time_type": "self",
            "tt_series": [],
            "maps": [],
            "page": page,
        },
    }
    resp = request_post(f"{E5_BASE}/mfilter/player/multidimension/list", body, HEADERS_5E)
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"5E 榜单接口异常: {data.get('message')}")
    return data["data"]["items"]


def fetch_e5_leaderboard(limit=100):
    log(f"5E：拉取 {YEAR_START[:10]} ~ {YEAR_END[:10]} 全等级赛事多维度榜单前 {limit} 名 ...")
    rows, page = [], 1
    while len(rows) < limit:
        batch = e5_multidimension_page(page)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 20:
            break
        page += 1
        time.sleep(SLEEP_5E)
    return rows[:limit]


def fetch_e5_yearly_stats(player_id, year):
    """5E 单选手指定年份的多维度统计。player_id 格式：csgo_pl_<数字ID>"""
    time.sleep(SLEEP_5E)
    body = {
        "dimension": "",
        "sort_key": "rating",
        "sort_value": "DESC",
        "player_options": {
            "tt_ids": [],
            "time_value": f"{year}-01-01 00:00:00_{year}-12-31 23:59:59",
            "grade": GRADES,
            "player_id": player_id,
            "time_type": "self",
            "tt_series": [],
            "maps": [],
            "page": 1,
        },
    }
    resp = request_post(f"{E5_BASE}/mfilter/player/multidimension/list", body, HEADERS_5E)
    data = resp.json()
    if not data.get("success"):
        return []
    return data["data"]["items"]


def extract_top20_players(top20_data):
    """从历年 Top20 数据中提取唯一选手列表 [(playerId, name), ...]"""
    seen = OrderedDict()
    for p in top20_data.get("allHltvTop20Players") or []:
        pid = p.get("playerId")
        if pid and pid not in seen:
            seen[pid] = p.get("playerName") or p.get("name") or ""
    return list(seen.items())


# ---------- 数据整理 ----------
def build_leaderboard_rows(players):
    """Sheet: 选手总榜（完美）"""
    rows = []
    for i, p in enumerate(players, 1):
        rows.append(OrderedDict([
            ("排名", i),
            ("选手ID", p.get("playerId")),
            ("选手", p.get("playerName")),
            ("战队", p.get("teamName") or "-"),
            ("战队ID", p.get("teamId")),
            ("地图数", p.get("mapsPlayed")),
            ("回合数", p.get("roundsPlayed")),
            ("击杀", p.get("kills")),
            ("死亡", p.get("deaths")),
            ("K/D", p.get("kdRatio")),
            ("Impact Rating", p.get("impactRating")),
        ]))
    return rows


def build_detail_rows(details):
    """Sheet: VS 顶级对手 Rating 拆分（Rating 3.0，含地图样本数）"""
    vs_rows, stat_rows, role_rows, honor_rows = [], [], [], []

    for d in details:
        pid = d.get("playerId")
        basic = d.get("basicInfo") or {}
        name = basic.get("playerName") or basic.get("name") or ""

        # vs Top-N 对手 Rating
        fr = d.get("featured_ratings_data") or {}
        row = OrderedDict([
            ("选手ID", pid),
            ("选手", name),
            ("Rating类型", fr.get("rating_type")),
        ])
        for item in fr.get("ratings") or []:
            desc = (item.get("description") or "").replace("vs ", "vs_").replace(" opponents", "")
            row[desc] = item.get("value")
            m = str(item.get("maps") or "").strip("()").replace(" maps", "")
            row[f"{desc}_地图数"] = m
        vs_rows.append(row)

        # 全量赛季统计
        psd = d.get("player_stats_data") or {}
        srow = OrderedDict([("选手ID", pid), ("选手", name)])
        for k in [
            ("maps_played", "地图数"), ("rounds_played", "回合数"),
            ("kills_per_round", "KPR"), ("deaths_per_round", "DPR"),
            ("assists_per_round", "APR"), ("dmg_per_round", "ADR"),
            ("grenade_dmg_per_round", "手雷伤害/回合"),
            ("KD_ratio", "K/D"), ("headshot_percent", "爆头率"),
            ("impact_rating", "Impact"),
            ("saved_teammates_per_round", "救队友/回合"),
            ("saved_by_teammate_per_round", "被队友救/回合"),
            ("kills", "击杀"), ("deaths", "死亡"),
        ]:
            srow[k[1]] = psd.get(k[0])
        # player_avg_data：各指标全榜百分位/评级
        pad = d.get("player_avg_data") or {}
        for metric, info in pad.items():
            if isinstance(info, dict):
                srow[f"{metric}_评级"] = info.get("grade")
                srow[f"{metric}_百分位"] = str(info.get("left_percent") or "").rstrip("%")
        # achievements：major 荣誉计数
        ach = basic.get("achievements") or {}
        for k, v in ach.items():
            srow[k] = v
        stat_rows.append(srow)

        # 角色化数据（残局/首杀等，取各角色 score 与关键 stats 叶子值）
        role = d.get("role_stats_data") or {}
        flat = flatten(role)
        rrow = OrderedDict([("选手ID", pid), ("选手", name)])
        for k, v in flat.items():
            if v in (None, "", "-"):
                continue
            k2 = k.replace("both_sides.", "").replace(".stats", "")
            # 只保留评分/胜率类数值，避免表过宽
            if k2.endswith("score") or "win_percentage" in k2 or "progress_width" in k2:
                rrow[k2] = str(v).rstrip("%") if isinstance(v, str) else v
        role_rows.append(rrow)

        # 荣誉明细（basicInfo.honorList：赛事荣誉 + 年度 HLTV 荣誉）
        for h in basic.get("honorList") or []:
            honor_rows.append(OrderedDict([
                ("选手ID", pid),
                ("选手", name),
                ("荣誉ID", h.get("id")),
                ("荣誉名称", (h.get("name") or "").strip()),
                ("名次", h.get("rank") or ""),
                ("类型", h.get("type")),
                ("日期", ms_to_date(h.get("timestamp"))),
                ("关联赛事", h.get("hasEvent")),
            ]))

    return vs_rows, stat_rows, role_rows, honor_rows


def build_top20_rows(top20):
    """Sheet: 历年 HLTV 官方 Top20（回测基准）"""
    rows = []
    for p in top20.get("allHltvTop20Players") or []:
        name = p.get("playerName") or p.get("name")
        pid = p.get("playerId")
        for h in p.get("honorList") or []:
            rows.append(OrderedDict([
                ("年份", h.get("id")),
                ("选手", name),
                ("选手ID", pid),
                ("官方名次", h.get("rank")),
            ]))
    rows.sort(key=lambda r: (-(r["年份"] or 0), int(r["官方名次"]) if str(r["官方名次"]).isdigit() else 99))
    return rows


def build_mvp_rows(mvp):
    """Sheet: 历年 MVP 统计（全部赛事 / 仅大赛 两口径）"""
    rows = []
    for scope, label in (("allEvents", "全部赛事"), ("onlyBigEvents", "仅大赛")):
        for p in mvp.get("allHltvMvps") or []:
            row = OrderedDict([
                ("口径", label),
                ("选手", p.get("playerName")),
                ("选手ID", p.get("playerId")),
            ])
            data = p.get(scope) or {}
            for y in sorted(data.keys()):
                if y == "Total":
                    continue
                row[f"20{y}"] = data[y]
            row["合计"] = data.get("Total")
            rows.append(row)
    return rows


def build_latest_honor_rows(data):
    rows = []
    for h in data.get("players") or []:
        rows.append(OrderedDict([
            ("选手", h.get("playerName")),
            ("选手ID", h.get("playerId")),
            ("战队", h.get("teamName")),
            ("赛事", h.get("eventName")),
            ("赛事ID", h.get("eventId")),
        ]))
    return rows


def build_e5_rows(items):
    """Sheet: 5E 年度多维度榜单"""
    rows = []
    for i, it in enumerate(items, 1):
        fv = it.get("field_values") or {}
        row = OrderedDict([
            ("排名", i),
            ("选手ID", it.get("player_id")),
            ("选手", it.get("player_name")),
        ])
        for k in sorted(fv.keys()):
            row[k] = fv[k]
        rows.append(row)
    return rows


def build_career_honor_rows(career_list):
    """Sheet: 历年生涯荣誉明细（完美 career 接口，逐赛事）
    type: 1=MVP 2=年度Top20 4=队伍名次(rank字段) 5=EVP
    注意：API 年份分组可能错位，日期列按时间戳推导"""
    rows = []
    for pid, name, career in career_list:
        for group in career or []:
            year = group.get("year")
            for h in group.get("csHonorList") or []:
                rows.append(OrderedDict([
                    ("选手ID", pid),
                    ("选手", name),
                    ("年份", year),
                    ("赛事名", (h.get("name") or "").strip()),
                    ("类型", h.get("type")),
                    ("名次", h.get("rank") or ""),
                    ("日期", ms_to_date(h.get("timestamp"))),
                    ("关联赛事", h.get("hasEvent")),
                    ("队友", ", ".join(pl.get("name", "") for pl in h.get("players") or [])),
                ]))
    rows.sort(key=lambda r: (-(r["年份"] or 0), r["选手ID"] or 0))
    return rows


def build_yearly_stats_rows(yearly_list):
    """Sheet: 5E 逐年统计（Top20 选手按年的多维度数据）
    Rating 为 5E 口径，勿与完美 Rating 3.0 混用"""
    rows = []
    for pid, name, year, items in yearly_list:
        if not items:
            continue
        fv = items[0].get("field_values") or {}
        rows.append(OrderedDict([
            ("选手ID", pid),
            ("选手", name),
            ("年份", year),
            ("地图数", fv.get("map_count")),
            ("Rating", fv.get("rating")),
            ("KAST", fv.get("kast")),
            ("ADR", fv.get("adr")),
            ("KPR", fv.get("kpr")),
            ("DPR", fv.get("dpr")),
            ("Impact", fv.get("impact")),
            ("Swing", fv.get("swing")),
            ("K/D", fv.get("kd")),
            ("KD差", fv.get("kddiff")),
            ("首杀", fv.get("first_blood")),
            ("首死", fv.get("first_death")),
            ("四杀", fv.get("kill4")),
            ("五杀", fv.get("kill5")),
            ("1v4", fv.get("v4")),
            ("1v5", fv.get("v5")),
            ("爆头率", fv.get("hs_rate")),
            ("胜率", fv.get("win_rate")),
        ]))
    rows.sort(key=lambda r: (-(r["年份"] or 0), r["选手ID"] or 0))
    return rows


# ---------- Excel 输出 ----------
HEADER_FILL = PatternFill("solid", fgColor="305496")
HEADER_FONT = Font(bold=True, color="FFFFFF")
CENTER = Alignment(horizontal="center", vertical="center")


def write_sheet(wb, title, rows, note=None):
    ws = wb.create_sheet(title[:31])
    start_row = 1
    if note:
        ws.cell(row=1, column=1, value=note)
        ws.cell(row=1, column=1).font = Font(italic=True, color="808080")
        start_row = 2
    if not rows:
        ws.cell(row=start_row, column=1, value="（无数据）")
        return ws
    headers = list(rows[0].keys())
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
    for r, row in enumerate(rows, start_row + 1):
        for c, h in enumerate(headers, 1):
            v = row.get(h)
            if isinstance(v, str):
                try:
                    v = float(v) if "." in v else int(v)
                except ValueError:
                    vv = v.strip().rstrip("%").replace("+", "")
                    try:
                        v = float(vv)
                    except ValueError:
                        pass
            ws.cell(row=r, column=c, value=v)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    # 列宽自适应（按表头与采样内容）
    for c, h in enumerate(headers, 1):
        width = max(len(str(h)), 6)
        for row in rows[:200]:
            width = max(width, min(len(str(row.get(h) or "")), 28))
        ws.column_dimensions[get_column_letter(c)].width = min(width + 2, 30)
    return ws


def save_excel(sheets):
    # 项目根 = src/ 的上一级（脚本从根目录移动过，不能再假设 __file__ 同级就是根）
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"CS2选手排名数据_{stamp}.xlsx")

    wb = Workbook()
    wb.remove(wb.active)

    # 说明页
    ws = wb.create_sheet("说明")
    info = [
        ("CS2 选手排名数据采集结果", ""),
        ("采集时间", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("数据来源1", "完美世界电竞数据 data.wanmei.com（Rating 口径对齐 HLTV，Rating 3.0）"),
        ("数据来源2", "5EPlay event.5eplay.com（自有 Rating 口径，仅作补充，勿与来源1混用加权）"),
        ("统计区间", f"{YEAR_START} ~ {YEAR_END}（5E 榜单；完美榜单/详情为平台当前赛季窗口）"),
        ("采集范围", f"选手总榜前 {TOP_N} 名及其详情；历年 Top20 选手生涯荣誉+逐年统计({HIST_YEAR_START}~{HIST_YEAR_END})"),
        ("工作表", ""),
        ("选手总榜_完美", "排名、地图/回合、K/D、Impact"),
        ("VS顶级对手Rating", "Rating 3.0 vs Top5/10/20/30/50 拆分（含地图样本数）"),
        ("选手详细统计", "KPR/DPR/ADR/KAST/爆头率等 + 全榜评级百分位 + Major 成就"),
        ("角色数据", "残局、首杀等角色化评分"),
        ("荣誉明细", "选手的赛事荣誉与年度荣誉列表"),
        ("历年HLTV_Top20", "官方年度名次（排名模型回测基准）"),
        ("MVP年度统计", "2012 年至今每年 MVP 数，分全部赛事/仅大赛"),
        ("近期赛事荣誉", "最新各赛事 MVP 归属"),
        ("5E年度数据榜", "5E 全等级赛事多维度榜单（Rating/KAST/ADR/Swing/首杀/多杀/残局）"),
        ("历年生涯荣誉", "完美 career 接口；Top20 选手逐赛事荣誉（MVP/EVP/队伍名次），2013 至今"),
        ("5E逐年统计", "5E 多维度逐年统计；Top20 选手按年的 Rating/ADR/KAST 等 18 项指标"),
        ("合规声明", "数据版权归原平台所有，本采集结果仅限个人学习/课程设计使用，请勿商用或二次分发"),
    ]
    for r, (k, v) in enumerate(info, 1):
        ws.cell(row=r, column=1, value=k).font = Font(bold=(r == 1 or v == ""))
        ws.cell(row=r, column=2, value=v)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 90

    for title, rows, note in sheets:
        write_sheet(wb, title, rows, note)

    wb.save(path)
    return path


# ---------- 主流程 ----------
def main():
    log("=== CS2 选手数据采集开始 ===")

    # 1. 完美：榜单
    players = fetch_wm_leaderboard()
    log(f"完美：榜单获取完成，共 {len(players)} 名选手")

    # 2. 完美：逐人详情
    details = []
    for i, p in enumerate(players, 1):
        pid = p.get("playerId")
        try:
            d = fetch_wm_detail(pid)
            if d:
                details.append(d)
        except Exception as e:
            log(f"  ! 选手 {p.get('playerName')}({pid}) 详情获取失败: {e}")
        if i % 10 == 0:
            log(f"  详情进度 {i}/{len(players)}")
    log(f"完美：详情获取完成，成功 {len(details)} 人")

    vs_rows, stat_rows, role_rows, honor_rows = build_detail_rows(details)

    # 3. 完美：历年 Top20 / MVP / 近期荣誉
    top20_raw = {}
    try:
        top20_raw = fetch_wm_top20()
        top20_rows = build_top20_rows(top20_raw)
    except Exception as e:
        log(f"! Top20 记录获取失败: {e}")
        top20_rows = []
    time.sleep(SLEEP_WM)
    try:
        mvp_rows = build_mvp_rows(fetch_wm_mvp())
    except Exception as e:
        log(f"! MVP 统计获取失败: {e}")
        mvp_rows = []
    time.sleep(SLEEP_WM)
    try:
        latest_rows = build_latest_honor_rows(fetch_wm_latest_honor())
    except Exception as e:
        log(f"! 近期荣誉获取失败: {e}")
        latest_rows = []

    # 4. 5E：年度多维度榜单
    try:
        e5_rows = build_e5_rows(fetch_e5_leaderboard(TOP_N))
    except Exception as e:
        log(f"! 5E 榜单获取失败: {e}")
        e5_rows = []

    # 5. 历年 Top20 选手：生涯荣誉 + 逐年统计（拟合用）
    top20_players = extract_top20_players(top20_raw)
    log(f"历史采集：{len(top20_players)} 名 Top20 选手，年份 {HIST_YEAR_START}~{HIST_YEAR_END}")

    # 5a. 完美 career：逐赛事荣誉（MVP/EVP/队伍名次）
    career_list = []
    for i, (pid, pname) in enumerate(top20_players, 1):
        try:
            career = fetch_wm_career(pid)
            career_list.append((pid, pname, career))
        except Exception as e:
            log(f"  ! career {pname}({pid}) 失败: {e}")
            career_list.append((pid, pname, []))
        if i % 20 == 0:
            log(f"  career 进度 {i}/{len(top20_players)}")
    career_honor_rows = build_career_honor_rows(career_list)
    log(f"  career 完成，共 {len(career_honor_rows)} 条荣誉记录")

    # 5b. 5E 逐年统计：单选手 × 逐年
    yearly_list = []
    total_queries = len(top20_players) * (HIST_YEAR_END - HIST_YEAR_START + 1)
    done = 0
    for pid, pname in top20_players:
        e5_pid = f"csgo_pl_{pid}"
        for year in range(HIST_YEAR_START, HIST_YEAR_END + 1):
            try:
                items = fetch_e5_yearly_stats(e5_pid, year)
                yearly_list.append((pid, pname, year, items))
            except Exception:
                yearly_list.append((pid, pname, year, []))
            done += 1
            if done % 100 == 0:
                log(f"  5E逐年 进度 {done}/{total_queries}")
    yearly_stats_rows = build_yearly_stats_rows(yearly_list)
    log(f"  5E逐年 完成，有效 {len(yearly_stats_rows)}/{total_queries} 条")

    sheets = [
        ("选手总榜_完美", build_leaderboard_rows(players), None),
        ("VS顶级对手Rating", vs_rows, "Rating 3.0；数值为对不同层级对手时的场均 Rating，地图数为样本量"),
        ("选手详细统计", stat_rows, "百分列为该指标在全部选手中所处位置（0-100，越大越好）"),
        ("角色数据", role_rows, "残局/首杀等角色化评分（0-100）"),
        ("荣誉明细", honor_rows, "类型：1=赛事荣誉 2=年度HLTV荣誉 5=其他（以平台定义为准）"),
        ("历年HLTV_Top20", top20_rows, "HLTV 官方年度名次，作为排名模型回测基准"),
        ("MVP年度统计", mvp_rows, "每年 MVP 奖牌数量；列名 19=2019 ... 26=2026"),
        ("近期赛事荣誉", latest_rows, None),
        ("5E年度数据榜", e5_rows, f"区间 {YEAR_START} ~ {YEAR_END}；含 Major/S+/S/A/资格赛A级"),
        ("历年生涯荣誉", career_honor_rows, "完美 career 接口；类型：1=MVP 2=年度Top20 4=队伍名次 5=EVP；API年份可能错位，以日期列为准"),
        ("5E逐年统计", yearly_stats_rows, "5E 多维度逐年统计（Top20 选手按年）；Rating 为 5E 口径，勿与完美 Rating 3.0 混用"),
    ]
    path = save_excel(sheets)
    counts = {name: len(rows) for name, rows, _ in sheets}
    log("=== 采集完成 ===")
    log(f"Excel 文件：{path}")
    for name, cnt in counts.items():
        log(f"  {name}: {cnt} 行")


if __name__ == "__main__":
    main()

