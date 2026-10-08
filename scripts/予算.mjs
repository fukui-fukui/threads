/**
 * AI の使用量を月ごとに足して、想定予算の何割まで来たかを見る
 * ------------------------------------------------------------------
 * 代表の指示（2026-10-08）「使用量を見てもらいたい。想定予算の60％超えたら教えて」。
 * - 福井（このリポジトリ）の state/usage.jsonl と、予算.json の「合わせて数えるリポジトリ」
 *   （石川など。公開リポジトリなので raw.githubusercontent.com から読む）を足す
 * - 結果を state/usage-summary.json に書く
 * - 「知らせる割合」を超えた月は、GitHub の Issue を1回だけ立てる（代表にメールで届く）
 * 金額は API の返事の usage から見積もった概算。請求とは少しずれる。
 * ------------------------------------------------------------------
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';

const 設定 = JSON.parse(readFileSync('予算.json', 'utf8'));
const REPO = process.env.GITHUB_REPOSITORY || 'fukui-fukui/threads';
const TOKEN = process.env.GITHUB_TOKEN || '';
const 今 = new Date(Date.now() + 9 * 3600 * 1000);
const 月 = process.env.MONTH || 今.toISOString().slice(0, 7);

function 行を読む(text) {
  return String(text || '').split('\n').filter((l) => l.trim()).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
}

const 出どころ = [{ 名: REPO, 行: existsSync('state/usage.jsonl') ? 行を読む(readFileSync('state/usage.jsonl', 'utf8')) : [] }];
for (const r of 設定['合わせて数えるリポジトリ'] ?? []) {
  try {
    const res = await fetch(`https://raw.githubusercontent.com/${r}/main/state/usage.jsonl?t=${Date.now()}`);
    出どころ.push({ 名: r, 行: res.ok ? 行を読む(await res.text()) : [] });
  } catch (e) {
    console.log(`::warning::${r} の使用量を読めませんでした（${e.message}）`);
    出どころ.push({ 名: r, 行: [], 読めず: true });
  }
}

const 内訳 = {};
let 合計 = 0;
for (const s of 出どころ) {
  for (const x of s.行) {
    if (!String(x.時刻 || '').startsWith(月)) continue;
    const 鍵 = `${s.名}｜${x.何}`;
    内訳[鍵] = Math.round(((内訳[鍵] ?? 0) + (x.ドル ?? 0)) * 1e4) / 1e4;
    合計 += x.ドル ?? 0;
  }
}
合計 = Math.round(合計 * 100) / 100;
const 予算 = 設定['月の予算ドル'];
const 割合 = 予算 ? 合計 / 予算 : 0;
const まとめ = { 月, 合計ドル: 合計, 予算ドル: 予算, 割合: Math.round(割合 * 1000) / 10 + '%', 内訳, 作成: 今.toISOString().slice(0, 16).replace('T', ' ') + ' JST' };
mkdirSync('state', { recursive: true });
writeFileSync('state/usage-summary.json', JSON.stringify(まとめ, null, 2) + '\n');
console.log(`${月}：概算 $${合計} ／ 予算 $${予算}（${まとめ.割合}）`);
if (process.env.GITHUB_STEP_SUMMARY) {
  const { appendFileSync } = await import('node:fs');
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, `## AI の使用量（${月}）\n\n概算 $${合計} ／ 予算 $${予算}（${まとめ.割合}）\n\n` + Object.entries(内訳).map(([k, v]) => `- ${k}: $${v}`).join('\n') + '\n');
}

for (const 線 of 設定['知らせる割合'] ?? []) {
  if (割合 < 線) continue;
  const 題 = `【予算】${月} の AI 使用量が想定予算の${Math.round(線 * 100)}%を超えました`;
  console.log(`::warning::${題}（概算 $${合計} ／ $${予算}）`);
  if (!TOKEN || process.env.DRY_RUN === '1') continue;
  const gh = (path, opt = {}) => fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...opt, headers: { authorization: `Bearer ${TOKEN}`, accept: 'application/vnd.github+json', 'content-type': 'application/json' },
  });
  const 既に = await (await gh(`/issues?state=all&per_page=100&labels=`)).json();
  if (Array.isArray(既に) && 既に.some((i) => i.title === 題)) continue;
  const 本文 = [
    `${月} の AI（Anthropic API）の使用量が、想定予算 $${予算} の${Math.round(線 * 100)}%を超えました。`,
    '',
    `- 概算：$${合計}（${まとめ.割合}）`,
    ...Object.entries(内訳).map(([k, v]) => `- ${k}：$${v}`),
    '',
    '金額は API の返事から見積もった概算です。正確な額は Anthropic の管理画面（Billing）で確かめてください。',
    'この知らせは scripts/予算.mjs が毎晩の確認で出しています（予算・割合は 予算.json）。',
  ].join('\n');
  const r = await gh('/issues', { method: 'POST', body: JSON.stringify({ title: 題, body: 本文 }) });
  console.log(r.ok ? `Issue を立てました：${題}` : `::warning::Issue を立てられませんでした（${r.status}）`);
}
