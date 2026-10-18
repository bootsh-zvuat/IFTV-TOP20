#!/usr/bin/env node
/**
 * IFTV 模拟器 —— 便携静态服务器（Node 版）
 *
 * 与 serve.py 等价，供没有 Python 的机器使用。
 * 零依赖，只用 Node 内置模块。
 *
 * 用法：
 *     node serve.js            # 默认 8000 端口
 *     node serve.js 9000       # 指定端口
 *     node serve.js --no-open  # 不自动打开浏览器
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');

const BASE_DIR = __dirname;
const DEFAULT_ROOT = path.join(BASE_DIR, 'if-simulator', 'dist');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json; charset=utf-8',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

function portInUse(port) {
  return new Promise((resolve) => {
    const s = net.connect({ host: '127.0.0.1', port }, () => {
      s.destroy();
      resolve(true);
    });
    s.on('error', () => resolve(false));
    s.setTimeout(500, () => {
      s.destroy();
      resolve(false);
    });
  });
}

async function pickPort(preferred) {
  for (let p = preferred; p < preferred + 30; p++) {
    if (!(await portInUse(p))) return p;
  }
  throw new Error(`从 ${preferred} 起连续 30 个端口都被占用`);
}

function openBrowser(url) {
  const plat = process.platform;
  try {
    if (plat === 'win32') {
      spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref();
    } else if (plat === 'darwin') {
      spawn('open', [url], { detached: true, stdio: 'ignore' }).unref();
    } else {
      spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
    }
  } catch (e) {
    // 打不开浏览器不算致命
  }
}

function serve(root, port) {
  const server = http.createServer((req, res) => {
    let urlPath;
    try {
      urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    } catch (e) {
      res.writeHead(400);
      return res.end('Bad Request');
    }

    let filePath = path.join(root, urlPath);
    // 防目录穿越：解析后必须仍在 root 之内
    // （只用 startsWith(root) 会放过与 root 同名前缀的兄弟目录，如 dist-verify/）
    const rel = path.relative(root, filePath);
    if (rel === '..' || rel.startsWith('..' + path.sep) || path.isAbsolute(rel)) {
      res.writeHead(403);
      return res.end('Forbidden');
    }

    // 目录 → index.html
    if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
      filePath = path.join(filePath, 'index.html');
    }
    // SPA 回退：非静态资源且不存在 → index.html
    if (!fs.existsSync(filePath) && !urlPath.startsWith('/assets/')) {
      filePath = path.join(root, 'index.html');
    }

    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        return res.end('404 Not Found: ' + urlPath);
      }
      const type = MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
      res.writeHead(200, {
        'Content-Type': type,
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
      });
      res.end(data);
    });
  });

  return new Promise((resolve, reject) => {
    // 端口在探测后被抢占等错误交给 main().catch 统一提示，而不是抛未处理异常
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

async function main() {
  const argv = process.argv.slice(2);
  const noOpen = argv.includes('--no-open');
  const rootIdx = argv.indexOf('--root');
  // 位置参数是端口；--root 后面跟的目录不能被当成端口
  const positional = argv.filter((a, i) => !a.startsWith('--') && !(rootIdx >= 0 && i === rootIdx + 1));
  const parsedPort = positional.length ? parseInt(positional[0], 10) : NaN;
  const wantPort = Number.isFinite(parsedPort) ? parsedPort : 8000;

  const root = path.resolve(rootIdx >= 0 && argv[rootIdx + 1] ? argv[rootIdx + 1] : DEFAULT_ROOT);

  if (!fs.existsSync(root)) {
    console.error(`错误：找不到目录 ${root}`);
    console.error('\n若尚未构建产物，请先执行：');
    console.error('    cd if-simulator');
    console.error('    npm ci');
    console.error('    npm run build');
    process.exit(1);
  }
  if (!fs.existsSync(path.join(root, 'index.html'))) {
    console.error(`错误：${root} 下没有 index.html`);
    process.exit(1);
  }

  const port = await pickPort(wantPort);
  const url = `http://localhost:${port}/`;
  await serve(root, port);

  console.log('='.repeat(60));
  console.log('  IFTV — CS2 选手年度排名与 If 线模拟器');
  console.log('='.repeat(60));
  console.log(`  服务目录 : ${root}`);
  console.log(`  访问地址 : ${url}`);
  if (port !== wantPort) console.log(`  （${wantPort} 被占用，已自动改用 ${port}）`);
  console.log('');
  console.log('  按 Ctrl+C 停止服务');
  console.log('='.repeat(60));
  console.log('');

  if (!noOpen) setTimeout(() => openBrowser(url), 1000);

  process.on('SIGINT', () => {
    console.log('\n已停止。');
    process.exit(0);
  });
}

main().catch((e) => {
  console.error('启动失败：' + e.message);
  process.exit(1);
});
