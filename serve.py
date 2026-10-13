# -*- coding: utf-8 -*-
"""
IFTV 模拟器 —— 便携静态服务器

为什么需要它：
  dist/index.html 不能双击打开。现代浏览器禁止 file:// 页面加载
  ES Module（Vite 产物必然是 module），实测报错：
    "Access to script at 'file:///...' from origin 'null' has been blocked
     by CORS policy: Cross origin requests are only supported for protocol
     schemes: ... http, https ..."
  因此必须经 HTTP 提供。

本脚本用 Python 标准库起一个本地 HTTP 服务并自动打开浏览器。
无第三方依赖，Python 3.7+ 即可。

用法：
    python serve.py            # 默认 8000 端口
    python serve.py 9000       # 指定端口
    python serve.py --no-open  # 不自动打开浏览器
"""
import argparse
import http.server
import os
import socket
import socketserver
import sys
import threading
import webbrowser

# 默认服务目录：本脚本所在目录下的 if-simulator/dist
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(BASE_DIR, "if-simulator", "dist")

# 不缓存，便于替换产物后立即生效
NO_CACHE = ("Cache-Control: no-store, no-cache, must-revalidate, max-age=0")


class Handler(http.server.SimpleHTTPRequestHandler):
    """静态文件处理器：SPA 回退 + 正确 MIME + 禁缓存"""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", NO_CACHE)
        super().end_headers()

    def log_message(self, fmt, *args):
        # 静音常规日志，保留错误
        code = args[1] if len(args) > 1 else ""
        if str(code).startswith(("4", "5")):
            sys.stderr.write("  [%s] %s\n" % (self.address_string(), fmt % args))

    def send_head(self):
        """单页应用：找不到的路径回退到 index.html（支持前端路由刷新）"""
        path = self.translate_path(self.path)
        if not os.path.exists(path) and not self.path.startswith("/assets/"):
            self.path = "/index.html"
        return super().send_head()


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def port_in_use(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def pick_port(preferred):
    """优先用指定端口；被占用则向后找一个空闲的"""
    for p in range(preferred, preferred + 30):
        if not port_in_use(p):
            return p
    raise RuntimeError("从 %d 起连续 30 个端口都被占用" % preferred)


def main():
    ap = argparse.ArgumentParser(description="IFTV 模拟器便携服务器")
    ap.add_argument("port", nargs="?", type=int, default=8000, help="端口（默认 8000）")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="静态文件目录")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：找不到目录 %s" % root)
        print()
        print("若尚未构建产物，请先执行：")
        print("    cd if-simulator")
        print("    npm ci")
        print("    npm run build")
        return 1
    if not os.path.exists(os.path.join(root, "index.html")):
        print("错误：%s 下没有 index.html" % root)
        return 1

    port = pick_port(args.port)
    url = "http://localhost:%d/" % port

    os.chdir(root)   # SimpleHTTPRequestHandler 以 cwd 为根
    handler = lambda *a, **kw: Handler(*a, directory=root, **kw)  # noqa: E731

    try:
        httpd = ThreadingServer(("127.0.0.1", port), handler)
    except OSError as e:
        print("启动失败：%s" % e)
        return 1

    print("=" * 60)
    print("  IFTV — CS2 选手年度排名与 If 线模拟器")
    print("=" * 60)
    print("  服务目录 : %s" % root)
    print("  访问地址 : %s" % url)
    if port != args.port:
        print("  （%d 被占用，已自动改用 %d）" % (args.port, port))
    print()
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)
    print()

    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
