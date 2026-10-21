// おでかけのフォームの自動メール（2026-10-20 代表 OK の文面）。
// 送るのは Resend（エキマエと同じ鍵 RESEND_API_KEY）。差出人は返信を受けない no-reply、返信先は contact@。
// 決済リンクはメールに入れない（仮押さえは申し込みの画面で済ませる）。

export const SITES: Record<string, { name: string; url: string }> = {
  fukui: { name: "ふくいおでかけ", url: "https://odekake.fukui-fukui.com" },
  ishikawa: { name: "いしかわおでかけ", url: "https://ishikawa-odekake.fukui-fukui.com" },
};
export const CONTACT = "contact@fukui-fukui.com";
export const PRICE_TEXT = "イベント掲載 1件 5,500円（税込）";
export const HOLD_DAYS = 7;

export type Mail = { to: string; subject: string; text: string; from: string; replyTo: string };
type Row = Record<string, unknown>;

const s = (v: unknown) => (v == null ? "" : String(v));
// クーポンで 0円になった申し込み（pay.ts の FREE）。仮押さえ・請求の文を出さない
const free = (r: Row) => r.payment_intent === "free";
const foot = () => [
  "",
  `ご連絡は ${CONTACT} までお願いします（このメールは送信専用です）。`,
];

function mail(region: string, to: string, subject: string, lines: string[]): Mail {
  const site = SITES[region] ?? SITES.fukui;
  return {
    to,
    subject: `【${site.name}】${subject}`,
    text: [...lines, ...foot(), "", site.name, site.url + "/"].join("\n"),
    from: `${site.name} <no-reply@fukui-fukui.com>`,
    replyTo: CONTACT,
  };
}

const KIND: Record<string, string> = { fix: "内容の誤り", remove: "掲載の取り下げ", paid: "有料のイベント掲載について", other: "そのほか" };

/** (1) お問い合わせの受付 */
export function inquiryReceived(r: Row): Mail {
  return mail(s(r.region), s(r.email), "お問い合わせを受け付けました", [
    `${s(r.name)} 様`,
    "",
    "お問い合わせありがとうございます。次の内容で受け付けました。",
    `・ご用件：${KIND[s(r.kind)] ?? "そのほか"}`,
    ...(s(r.page) ? [`・関係するページや催し：${s(r.page)}`] : []),
    "・内容：",
    s(r.message),
    "",
    `お返事が必要な内容には、数日以内に ${CONTACT} からご連絡します。少しお時間をいただくことがあります。`,
  ]);
}

function summary(r: Row): string[] {
  const date = s(r.date_to) && s(r.date_to) !== s(r.date_from) ? `${s(r.date_from)} 〜 ${s(r.date_to)}` : s(r.date_from);
  return [
    `・申込番号：${s(r.number)}`,
    `・催し：${s(r.event_name)}`,
    `・開催日：${date}${s(r.time_text) ? `　${s(r.time_text)}` : ""}`,
    `・会場：${s(r.venue)}（${s(r.city)}）`,
    `・主催者：${s(r.organizer)}`,
    `・公式の URL：${s(r.official_url)}`,
    `・チラシ：${r.flyer_path ? "あり" : "なし"}`,
  ];
}

/** (2) 掲載のお申し込みの受付（仮押さえ済み） */
export function submissionReceived(r: Row): Mail {
  const site = SITES[s(r.region)] ?? SITES.fukui;
  return mail(s(r.region), s(r.contact_email), `イベント掲載のお申し込みを受け付けました（申込番号 ${s(r.number)}）`, [
    `${s(r.contact_name)} 様`,
    "",
    "お申し込みありがとうございます。次の内容で受け付けました。",
    ...summary(r),
    ...(free(r) ? [
      "・料金：クーポンのご利用で 0円です（請求はありません）",
      "",
      "これから、主催者などの公式の案内で内容を確かめます。",
      "掲載が決まったら、掲載を始める日をお知らせします。",
      `掲載できない場合や、${HOLD_DAYS}日以内に掲載を決められなかった場合も、メールでお知らせします。`,
    ] : [
      `・料金：${PRICE_TEXT}。カードで仮押さえしています。まだ確定していません`,
      "",
      "これから、主催者などの公式の案内で内容を確かめます。",
      "掲載が決まったら仮押さえを確定し、掲載を始める日をお知らせします。",
      "掲載できない場合は仮押さえを取り消し、料金は請求されません。",
      `${HOLD_DAYS}日以内に掲載を決められなかった場合も、仮押さえを取り消します。`,
    ]),
    "",
    `特定商取引法に基づく表記：${site.url}/tokushoho/`,
  ]);
}

/** (3) 掲載決定（確定） */
export function submissionCaptured(r: Row): Mail {
  return mail(s(r.region), s(r.contact_email), `イベント掲載が決まりました（申込番号 ${s(r.number)}）`, [
    `${s(r.contact_name)} 様`,
    "",
    `「${s(r.event_name)}」の掲載が決まりました。`,
    free(r) ? "クーポンのご利用のため、料金はかかりません。" : `${PRICE_TEXT}を確定しました。Stripe から領収書をお送りします。`,
    "掲載は、確定した日から3日以内に始めます。表示や投稿には「PR」と付きます。",
  ]);
}

/** (4) お断り（取り消し） */
export function submissionCanceled(r: Row): Mail {
  return mail(s(r.region), s(r.contact_email), `イベント掲載のお申し込みについて（申込番号 ${s(r.number)}）`, [
    `${s(r.contact_name)} 様`,
    "",
    `「${s(r.event_name)}」のお申し込みについて、内容を確かめた結果、今回は掲載を見送ることになりました。`,
    free(r) ? "料金はかかっていません。" : "仮押さえは取り消しましたので、料金は請求されません（カード会社によって、表示が消えるまで数日かかることがあります）。",
  ]);
}

/** (5) 期限切れ */
export function submissionExpired(r: Row): Mail {
  return mail(s(r.region), s(r.contact_email), `イベント掲載のお申し込みについて（申込番号 ${s(r.number)}）`, [
    `${s(r.contact_name)} 様`,
    "",
    free(r) ? `「${s(r.event_name)}」のお申し込みから${HOLD_DAYS}日以内に掲載を決められなかったため、お申し込みを取り消しました（料金はかかっていません）。`
      : `「${s(r.event_name)}」のお申し込みから${HOLD_DAYS}日以内に掲載を決められなかったため、仮押さえを取り消しました（請求はされません）。`,
    "お手数ですが、掲載を希望される場合は改めてお申し込みください。",
  ]);
}

/** 運営あて（contact@ → 代表の Gmail）：届いたことだけを知らせる。中身はダッシュボードで見る（2026-10-21 代表「B」） */
export function noticeSubmission(r: Row): Mail {
  const site = SITES[s(r.region)] ?? SITES.fukui;
  return mail(s(r.region), CONTACT, `新しい掲載の申し込み（申込番号 ${s(r.number)}）`, [
    `${site.name}に、イベント掲載の申し込みが届きました。`,
    `・申込番号：${s(r.number)}`,
    `・催し：${s(r.event_name)}`,
    `・料金：${free(r) ? "無料（クーポン）" : r.payment_intent ? "5,500円を仮押さえ済み（未確定）" : "まだお支払いなし（仮押さえを使っていないとき）"}`,
    "",
    "全項目とチラシは、ダッシュボードの「掲載申込」で見られます（反映は毎朝 8:30 ごろ。急ぐときは統括へ）。",
    "「受ける／受けない」は、仮押さえの期限（7日）までに選んでください。",
  ]);
}

export function noticeInquiry(r: Row): Mail {
  const site = SITES[s(r.region)] ?? SITES.fukui;
  return mail(s(r.region), CONTACT, `新しいお問い合わせ（${KIND[s(r.kind)] ?? "そのほか"}）`, [
    `${site.name}に、お問い合わせが届きました。`,
    `・ご用件：${KIND[s(r.kind)] ?? "そのほか"}`,
    `・お名前：${s(r.name)}`,
    "",
    "中身とメールアドレスは、ダッシュボードの「問合せ」で見られます（反映は毎朝 8:30 ごろ）。",
  ]);
}

/** Resend で送る。鍵が無ければ送らずに false */
export async function send(m: Mail): Promise<boolean> {
  const key = Deno.env.get("RESEND_API_KEY");
  if (!key || !m.to) return false;
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: m.from, to: [m.to], subject: m.subject, text: m.text, reply_to: m.replyTo }),
  });
  if (!res.ok) {
    console.error("Resend", res.status, await res.text());
    return false;
  }
  return true;
}
