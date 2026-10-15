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
// 使用量は 10/13 から非公開の置き場（odekake-data）に移った。公開リポジトリの state/usage.jsonl は 404 になり、
// 石川の分が黙って0として数えられていた（2026-10-15 気づいて直す）。置き場の写しがあればそちらを読む
const 置き場 = process.env.DATA_CLONE || (process.env.RUNNER_TEMP || '/tmp') + '/odekake-data';
const 置き場の名 = { 'yu-fukui/ishikawa-odekake': 'ishikawa', ...(設定['置き場の名'] ?? {}) };
for (const r of 設定['合わせて数えるリポジトリ'] ?? []) {
  const 写し = 置き場の名[r] ? `${置き場}/${置き場の名[r]}/state/usage.jsonl` : '';
  if (写し && existsSync(写し)) {
    出どころ.push({ 名: r, 行: 行を読む(readFileSync(写し, 'utf8')) });
    continue;
  }
  try {
    const res = await fetch(`https://raw.githubusercontent.com/${r}/main/state/usage.jsonl?t=${Date.now()}`);
    if (!res.ok) console.log(`::warning::${r} の使用量を読めませんでした（${res.status}。非公開の置き場の写しも無い）`);
    出どころ.push({ 名: r, 行: res.ok ? 行を読む(await res.text()) : [], 読めず: !res.ok });
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
// 公開リポジトリのログ・ジョブの概要・Issue には金額を出さず、予算に対する割合だけにする（2026-10-15）。
// 金額は非公開の置き場の state/usage-summary.json で見る
console.log(`${月}：予算の ${まとめ.割合}`);
if (process.env.GITHUB_STEP_SUMMARY) {
  const { appendFileSync } = await import('node:fs');
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, `## AI の使用量（${月}）\n\n予算の ${まとめ.割合}（金額は非公開の置き場の state/usage-summary.json）\n`);
}

await 知らせる(設定['知らせる割合'] ?? [], '', 合計, 予算, 割合, まとめ.割合, 内訳);

/**
 * 「別に数える」：予算を分けて見るサイト（ぎふあいちなど。2026-10-15 代表「API キーは別で用意します」「月50ドル」）。
 * 非公開の置き場（odekake-data。budget-check の最初の pull で手元に取ってある）の <置き場>/state/usage.jsonl を読む。
 * Issue の題には【予算・名】と付けて、福井＋石川の予算とは混ぜない。
 */
for (const 別 of 設定['別に数える'] ?? []) {
  const パス = `${process.env.DATA_CLONE || (process.env.RUNNER_TEMP || '/tmp') + '/odekake-data'}/${別.置き場}/state/usage.jsonl`;
  if (!existsSync(パス)) console.log(`::notice::${別.名} の使用量はまだありません（${パス}）`);
  const 別の内訳 = {};
  let 別の合計 = 0;
  for (const x of existsSync(パス) ? 行を読む(readFileSync(パス, 'utf8')) : []) {
    if (!String(x.時刻 || '').startsWith(月)) continue;
    別の内訳[x.何] = Math.round(((別の内訳[x.何] ?? 0) + (x.ドル ?? 0)) * 1e4) / 1e4;
    別の合計 += x.ドル ?? 0;
  }
  別の合計 = Math.round(別の合計 * 100) / 100;
  const 別の割合 = 別.月の予算ドル ? 別の合計 / 別.月の予算ドル : 0;
  const 別のまとめ = { 割合: Math.round(別の割合 * 1000) / 10 + '%' };
  // まとめはファイルにしない（公開リポジトリに金額を残さない）。ログとジョブの概要にだけ出す
  console.log(`${別.名} ${月}：予算の ${別のまとめ.割合}`);
  if (process.env.GITHUB_STEP_SUMMARY) {
    const { appendFileSync } = await import('node:fs');
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `\n## AI の使用量・${別.名}（${月}）\n\n予算の ${別のまとめ.割合}\n`);
  }
  await 知らせる(別.知らせる割合 ?? [], 別.名, 別の合計, 別.月の予算ドル, 別の割合, 別のまとめ.割合, 別の内訳);
}

async function 知らせる(線たち, 名, 合計, 予算, 割合, 割合の字, 内訳) {
  for (const 線 of 線たち) {
    if (割合 < 線) continue;
    const 題 = `【予算${名 ? '・' + 名 : ''}】${月} の AI 使用量が想定予算の${Math.round(線 * 100)}%を超えました`;
    console.log(`::warning::${題}（予算の ${割合の字}）`);
    if (!TOKEN || process.env.DRY_RUN === '1') continue;
    const gh = (path, opt = {}) => fetch(`https://api.github.com/repos/${REPO}${path}`, {
      ...opt, headers: { authorization: `Bearer ${TOKEN}`, accept: 'application/vnd.github+json', 'content-type': 'application/json' },
    });
    const 既に = await (await gh(`/issues?state=all&per_page=100&labels=`)).json();
    if (Array.isArray(既に) && 既に.some((i) => i.title === 題)) continue;
    const 本文 = [
      `${月} の AI（Anthropic API）の使用量が、想定予算の${Math.round(線 * 100)}%を超えました（いま ${割合の字}）。`,
      '',
      'このリポジトリは公開なので、金額と内訳はここに書きません。非公開の置き場（odekake-data）の state/usage-summary.json か、',
      'Anthropic の管理画面（Billing）で確かめてください。',
      'この知らせは scripts/予算.mjs が毎晩の確認で出しています（予算・割合は 予算.json）。',
    ].join('\n');
    const r = await gh('/issues', { method: 'POST', body: JSON.stringify({ title: 題, body: 本文 }) });
    console.log(r.ok ? `Issue を立てました：${題}` : `::warning::Issue を立てられませんでした（${r.status}）`);
  }
}
