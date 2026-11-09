// 3選リールの場面を、Claude Code が描いた絵（HTML・SVG）から5秒の動画にする。
//
// 2026-11-09 代表（統括経由）：3選リールは「C：AIだけで作る（代表の Gemini・Vids の素材なし）」。
// 写真は使わない（使用許可のない画像は使わない）。費用はかからない（chromium と ffmpeg だけ）。
//
// 使い方:
//   node scripts/場面.mjs scripts/場面/そば.html 出力.mp4 [--sec 5] [--fps 24]
//
// 場面の HTML は window.renderAt(t) を持ち、t 秒の絵を描く（同じ t なら必ず同じ絵。乱数は種つき）。
// 一コマずつ撮って ffmpeg でつなぐ考え方は Vincentwei1021/mg-styles-15（MIT）の harness/render.mjs を参考にした。
// 画面は 720×1280。上の 400px は scripts/リール.py のテロップの帯が乗るので、主役は下 2/3 に描く。
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

// playwright は全体に入っているものを使う（ESM の import では見つからないので require で読む）
const { chromium } = createRequire(import.meta.url)('playwright');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(`--${k}`); return i >= 0 ? Number(args[i + 1]) : d; };
const [page_path, out] = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--')));
if (!page_path || !out) {
  console.error('使い方: node scripts/場面.mjs 場面.html 出力.mp4 [--sec 5] [--fps 24]');
  process.exit(1);
}
const SEC = opt('sec', 5), FPS = opt('fps', 24), W = 720, H = 1280;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H } });
await page.goto(pathToFileURL(path.resolve(page_path)).href);
await page.waitForFunction(() => typeof window.renderAt === 'function');

const ff = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS),
  '-c:v', 'png', '-i', '-', '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', out], { stdio: ['pipe', 'inherit', 'inherit'] });
const done = new Promise((res, rej) => ff.on('close', (c) => (c === 0 ? res() : rej(new Error(`ffmpeg ${c}`)))));

const frames = Math.round(SEC * FPS);
for (let f = 0; f < frames; f++) {
  await page.evaluate((t) => window.renderAt(t), f / FPS);
  const png = await page.screenshot({ type: 'png', clip: { x: 0, y: 0, width: W, height: H } });
  if (!ff.stdin.write(png)) await new Promise((r) => ff.stdin.once('drain', r));
}
ff.stdin.end();
await done;
await browser.close();
console.log(`できた：${out}（${frames}コマ）`);
