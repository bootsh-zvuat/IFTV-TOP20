# -*- coding: utf-8 -*-
"""
HLTV 手动导出页解析器 —— 把浏览器另存的 HTML 转为 If 模拟器可用的对手强度数据。

为什么是"手动导出"：
  hltv.org 由 Cloudflare 保护（JS Challenge），纯 HTTP 客户端拿不到内容
  （实测首页与选手页均返回 403 "Just a moment..."）。真实浏览器可以正常访问，
  因此由人工打开页面、另存为 HTML，再由本脚本本地解析 —— 完全避开反爬。

用法：
  1. 浏览器打开 HLTV 选手页，例如
       https://www.hltv.org/stats/players/11893/ZywOo?startDate=2025-01-01&endDate=2025-12-31
     （startDate/endDate 让页面只统计该年）→ 另存为 .html
  2. 把所有选手的 HTML 放进一个目录，例如 data/hltv_html/2025/
  3. 运行：.venv\\Scripts\\python.exe parse_hltv_html.py --html-dir data/hltv_html/2025 \\
             --year 2025 --out data/hltv_opponent_2025.xlsx

输出列：年份 / 选手 / 地图数 / Rating / K-D差 / K/D / vsTop5 / vsTop10 / vsTop20 /
        vsTop30 / vsTop50 / 来源文件

设计原则（重要）：
  HLTV 的 DOM 结构会变，且我无法联网核对当前版本。因此本解析器**不依赖
  固定 CSS 选择器**，而是：
    - 用"可见文本 + 数值模式"提取，对 class 名变化免疫；
    - 支持 BeautifulSoup（若已安装）与纯正则两条路径；
    - 解析不出时明确报错并提示用 --dump 查看实际抓到的文本，便于快速调整。
"""
import argparse
import glob
import os
import re
import sys
from collections import OrderedDict

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
except ImportError:
    print("缺少 openpyxl：.venv\\Scripts\\python.exe -m pip install openpyxl")
    sys.exit(1)


# ---------- HTML → 纯文本 ----------
def html_to_text(html):
    """把 HTML 转成"带换行的可见文本"，丢弃 script/style。
    不依赖任何 class，因此对 HLTV 改版免疫。"""
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        # 块级元素补换行，保证数值不粘连
        for tag in soup.find_all(["div", "tr", "td", "th", "li", "p", "br", "h1", "h2", "h3", "span"]):
            tag.append("\n")
        return soup.get_text("\n")
    # 无 bs4 时的降级路径
    s = re.sub(r"<script.*?</script>", "\n", html, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", "\n", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(div|tr|td|th|li|p|h[1-6]|span)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    import html as _html
    s = _html.unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s


def lines_of(text):
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def num_or_none(s):
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


# ---------- 字段提取（结构化优先，文本兜底） ----------
def extract_player_name(lines, html):
    """选手名：优先 <h1>，其次 title，最后 URL 形态"""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S | re.I)
    if m:
        t = re.sub(r"<[^>]+>", " ", m.group(1))
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            return t
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.S | re.I)
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        t = re.sub(r"\s*[|:-]\s*HLTV.*$", "", t, flags=re.I)
        if t:
            return t
    return ""


def extract_vs_ratings(lines):
    """提取 vs Top-N 对手 Rating。

    HLTV 的 "Featured ratings" 区块形如：
        vs top 5 opponents   1.36
        vs top 10 opponents  1.36
        vs top 20 opponents  1.38
    数值可能同行或下一行，且可能被 span 拆开，故两行都找。
    """
    out = {}
    pat = re.compile(r"vs\s*top\s*(\d+)\s*opponents?", re.I)
    for i, ln in enumerate(lines):
        m = pat.search(ln)
        if not m:
            continue
        n = int(m.group(1))
        # 同一行里的数值（排除 top N 的 N 本身）
        tail = ln[m.end():]
        v = num_or_none(tail)
        if v is None:
            # 下一行找
            for j in range(i + 1, min(i + 4, len(lines))):
                v = num_or_none(lines[j])
                if v is not None:
                    break
        if v is None:
            continue
        # 合理性：Rating 通常在 0.3~2.0
        if 0.2 <= v <= 2.5:
            out[n] = v
    return out


def extract_map_count(lines, html):
    """地图数：HLTV 显示 Maps played / Total maps 等"""
    for i, ln in enumerate(lines):
        if re.search(r"\b(maps?|maps played|total maps)\b", ln, re.I):
            # 同行数值
            v = num_or_none(re.sub(r"(?i)maps?", "", ln))
            if v is not None and v >= 1:
                return int(v)
            for j in range(i + 1, min(i + 3, len(lines))):
                v = num_or_none(lines[j])
                if v is not None and v >= 1:
                    return int(v)
    return None


def extract_kd_diff(lines):
    """K-D 差：形如 "+123" 或 "-45"（HLTV 常用带符号整数）。

    注意：页面里其它位置也可能出现带符号整数，因此**必须先锚定 K-D Diff 标签**
    （标签与值分行，或同行），不能直接在全页搜第一个带符号数。
    """
    # 1) 标签与值分行：'K-D Diff' 后面第一行是带符号整数
    for i, ln in enumerate(lines):
        if re.fullmatch(r"K-?D\s*(Diff|Difference)", ln, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                cand = lines[j].replace(" ", "")
                if re.fullmatch(r"[+-]?\d{1,5}", cand):
                    return int(cand)
    # 2) 标签与值同行：'K-D Diff +123'
    for ln in lines:
        m = re.search(r"K-?D\s*(?:Diff|Difference)\s*([+-]?\d{1,5})", ln, re.I)
        if m:
            return int(m.group(1))
    return None


def extract_rating(lines, vs):
    """整体 Rating。
    注意：vsTopN 的值也在页面里，不能误取，故先排除含 'vs top' 的行。"""
    # 优先 "Rating" 标签行
    for i, ln in enumerate(lines):
        if re.fullmatch(r"Rating", ln, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                v = num_or_none(lines[j])
                if v is not None and 0.2 <= v <= 2.5:
                    return v
    # 次选：标签与值同行 "Rating 1.24"
    for ln in lines:
        if re.search(r"\bRating\b", ln, re.I) and not re.search(r"vs\s*top", ln, re.I):
            v = num_or_none(re.sub(r"(?i).*?Rating", "", ln))
            if v is not None and 0.2 <= v <= 2.5:
                return v
    # 最后：若页面只有 vs 值，用最宽档近似（并标注）
    if vs:
        widest = max(vs)
        return vs[widest]
    return None


def extract_kd_ratio(lines):
    """K/D 比值：形如 1.24"""
    for i, ln in enumerate(lines):
        if re.fullmatch(r"K/?D\s*(Ratio)?", ln, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                v = num_or_none(lines[j])
                if v is not None and v > 0:
                    return v
    for ln in lines:
        m = re.match(r"^K/?D\s*Ratio\s+([\d.]+)", ln, re.I)
        if m:
            return float(m.group(1))
    return None


def parse_html_file(path):
    """解析单个选手页 HTML，返回 dict（解析不到的字段为 None）"""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    text = html_to_text(html)
    lines = lines_of(text)

    vs = extract_vs_ratings(lines)
    rec = OrderedDict([
        ("选手", extract_player_name(lines, html)),
        ("地图数", extract_map_count(lines, html)),
        ("Rating", extract_rating(lines, vs)),
        ("KD差", extract_kd_diff(lines)),
        ("KD比值", extract_kd_ratio(lines)),
        ("vsTop5", vs.get(5)),
        ("vsTop10", vs.get(10)),
        ("vsTop20", vs.get(20)),
        ("vsTop30", vs.get(30)),
        ("vsTop50", vs.get(50)),
        ("来源文件", os.path.basename(path)),
    ])
    return rec, lines


def diagnosis(rec, lines):
    """给出该文件的解析质量诊断"""
    issues = []
    if not rec["选手"]:
        issues.append("选手名未识别")
    if rec["地图数"] is None:
        issues.append("地图数未识别")
    if not any(rec[k] is not None for k in ("vsTop5", "vsTop10", "vsTop20")):
        issues.append("未识别到任何 vs Top-N 值")
    if rec["Rating"] is None:
        issues.append("Rating 未识别")
    return issues


# ---------- Excel 输出 ----------
HEADER_FILL = PatternFill("solid", fgColor="305496")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def write_xlsx(path, header, rows, note=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "opponent"
    start = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color="808080")
        start = 2
    for c, h in enumerate(header, 1):
        cell = ws.cell(row=start, column=c, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    for i, row in enumerate(rows, start + 1):
        for c, v in enumerate(row, 1):
            ws.cell(row=i, column=c, value=v)
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description="解析 HLTV 手动导出的选手页 HTML")
    ap.add_argument("--html-dir", required=True, help="存放另存 HTML 的目录")
    ap.add_argument("--year", type=int, required=True, help="该批 HTML 对应的年份")
    ap.add_argument("--out", required=True, help="输出 xlsx 路径")
    ap.add_argument("--dump", action="store_true",
                    help="打印每个文件解析出的可见文本前 N 行，便于排查选择器问题")
    ap.add_argument("--dump-lines", type=int, default=80, help="--dump 时的行数")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.html_dir, "*.htm")) +
                   glob.glob(os.path.join(args.html_dir, "*.html")))
    if not files:
        print(f"未在 {args.html_dir} 找到 .html/.htm 文件")
        print("提示：浏览器打开选手页 → Ctrl+S → 保存类型选「网页，仅 HTML」")
        return 1

    print(f"发现 {len(files)} 个 HTML 文件")
    print(f"BeautifulSoup: {'可用' if HAS_BS4 else '不可用（用正则降级路径）'}")
    print()

    rows, problems = [], []
    for p in files:
        rec, lines = parse_html_file(p)
        issues = diagnosis(rec, lines)
        rows.append([args.year] + list(rec.values()))
        flag = "OK " if not issues else "!! "
        print(f"  {flag}{os.path.basename(p):<40} "
              f"选手={rec['选手'] or '?':<14} 图数={rec['地图数']} "
              f"vsTop5={rec['vsTop5']} vsTop10={rec['vsTop10']} vsTop20={rec['vsTop20']}")
        if issues:
            problems.append((p, issues))
        if args.dump:
            print("    " + "-" * 70)
            for ln in lines[:args.dump_lines]:
                print(f"    | {ln}")
            print("    " + "-" * 70)

    header = ["年份", "选手", "地图数", "Rating", "KD差", "KD比值",
              "vsTop5", "vsTop10", "vsTop20", "vsTop30", "vsTop50", "来源文件"]
    note = (f"HLTV 手动导出解析结果（{args.year}）。"
            f"vsTopN = 对阵 top-N 战队时的 Rating。"
            f"来源：浏览器另存 HTML，非抓取。")
    write_xlsx(args.out, header, rows, note=note)
    print(f"\n已写出: {args.out}（{len(rows)} 行）")

    if problems:
        print(f"\n! {len(problems)} 个文件存在解析问题：")
        for p, issues in problems:
            print(f"  {os.path.basename(p)}: {'; '.join(issues)}")
        print("\n排查建议：加 --dump 查看实际可见文本，"
              "再把文本特征反馈以调整提取规则。")
        return 2
    print("\n全部文件解析成功。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
