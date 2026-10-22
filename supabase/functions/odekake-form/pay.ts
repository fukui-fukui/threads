// イベント掲載の仮押さえ（2026-10-20 代表：申し込みと同時にカードで 5,500円を仮押さえ → 代表が「受ける」で確定、「受けない」で取り消し）。
// Stripe の Checkout（payment_intent_data.capture_method = manual）を API で作る。Webhook は使わず、
// 戻ってきたとき（confirm）と毎朝の処理（process）で Stripe に問い合わせて状態をそろえる。
// 鍵：試験なら STRIPE_TEST_SECRET_KEY、ほかは STRIPE_SECRET_KEY（エキマエと同じ鍵）。

export const AMOUNT = 5500;
// 支払いボタンのすぐ上に出す文（2026-10-21 代表 OK の (a)）
export const SUBMIT_TEXT = "いまはカードの仮押さえです。掲載が決まった時点で 5,500円（税込）を請求します。掲載できない場合や、7日以内に掲載を決められなかった場合は仮押さえを取り消し、請求はありません。クーポンで0円になる場合は、請求はありません。";
// クーポンで 0円になった申し込み（Stripe は仮押さえを作らない）の印。payment_intent の欄にこの値を入れる
export const FREE = "free";
// 初回のお申し込みで無料にしたもの（2026-10-22 代表「進めて」）。Stripe を通さないので、確定・取り消しで Stripe を呼ばない
export const FIRST = "first";
/** 請求の無い申し込み（クーポンで 0円・初回無料）か */
export const noCharge = (pi: unknown) => pi === FREE || pi === FIRST;
// 仮押さえはカードでふつう7日で切れる。切れる前に余裕をもって取り消す（6日と12時間）
export const HOLD_LIMIT_MS = 6.5 * 24 * 3600_000;
// 何日目に「もうすぐ切れる」を出すか
export const REMIND_MS = 5 * 24 * 3600_000;

let test = false;
/** 試験の鍵を使うか（odekake_settings の pay_mode=test か、合言葉つきの試験の送信） */
export function useTest(on: boolean) { test = on; }
export const isTest = () => test;

function key(): string {
  const k = test ? Deno.env.get("STRIPE_TEST_SECRET_KEY") : Deno.env.get("STRIPE_SECRET_KEY");
  if (!k) throw new Error("stripe key");
  return k;
}

/** {a: {b: 1}} → a[b]=1 の形（Stripe の API が受ける形） */
export function form(obj: Record<string, unknown>, prefix = ""): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null) continue;
    const name = prefix ? `${prefix}[${k}]` : k;
    if (typeof v === "object") out.push(...form(v as Record<string, unknown>, name));
    else out.push(`${encodeURIComponent(name)}=${encodeURIComponent(String(v))}`);
  }
  return out;
}

async function api(method: string, path: string, body?: Record<string, unknown>) {
  const r = await fetch(`https://api.stripe.com/v1/${path}`, {
    method,
    headers: { Authorization: `Bearer ${key()}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: body ? form(body).join("&") : undefined,
  });
  const j = await r.json();
  if (!r.ok) throw new Error(`stripe ${r.status} ${j?.error?.code ?? ""} ${j?.error?.message ?? ""}`);
  return j;
}

export function checkoutBody(o: { number: string; region: string; siteName: string; siteUrl: string; email: string; eventName: string }) {
  return {
    mode: "payment",
    locale: "ja",
    client_reference_id: o.number,
    customer_email: o.email,
    expires_at: Math.floor(Date.now() / 1000) + 30 * 60,   // 30分で切れる（Stripe の下限）
    line_items: { 0: { quantity: 1, price_data: { currency: "jpy", unit_amount: AMOUNT,
      product_data: { name: `イベント掲載（${o.siteName}）`, description: `申込番号 ${o.number}：${o.eventName}`.slice(0, 200) } } } },
    // Managed Payments（Stripe が売り手になる仕組み）は使わない。販売事業者はふくふくプロジェクト（2026-10-21 代表）
    managed_payments: { enabled: "false" },
    payment_method_types: { 0: "card" },
    // クーポン（プロモーションコード）を入れる欄を出す（2026-10-21 代表。WASHOOI2026 など）
    allow_promotion_codes: "true",
    custom_text: { submit: { message: SUBMIT_TEXT } },
    payment_intent_data: { capture_method: "manual", description: `イベント掲載 ${o.number}`,
      metadata: { number: o.number, region: o.region } },
    metadata: { number: o.number, region: o.region, kind: "odekake-submission" },
    success_url: `${o.siteUrl}/submit/?n=${encodeURIComponent(o.number)}&s={CHECKOUT_SESSION_ID}`,
    cancel_url: `${o.siteUrl}/submit/?n=${encodeURIComponent(o.number)}&cancel=1`,
  };
}

export const createCheckout = (b: Record<string, unknown>) => api("POST", "checkout/sessions", b);
export const getSession = (id: string) => api("GET", `checkout/sessions/${encodeURIComponent(id)}?expand[]=payment_intent`);
export const capture = (pi: string) => api("POST", `payment_intents/${encodeURIComponent(pi)}/capture`, {});
export const cancel = (pi: string) => api("POST", `payment_intents/${encodeURIComponent(pi)}/cancel`, {});
export const account = () => api("GET", "account");

/** Checkout の結果から、仮押さえが済んだか（payment_intent が requires_capture）を返す。
 *  クーポンで 0円になって完了したもの（Stripe は仮押さえを作らない）は FREE を返す */
export function heldIntent(session: Record<string, unknown>, number: string): string | null {
  if (session.client_reference_id !== number) return null;
  // 合計 0円で完了したもの。payment_status は「no_payment_required」とも「paid」とも返るので見ない（2026-10-21 本番で取りこぼした）
  if (session.status === "complete" && Number(session.amount_total) === 0) return FREE;
  const pi = session.payment_intent as Record<string, unknown> | string | null;
  if (pi && typeof pi === "object" && pi.status === "requires_capture") return String(pi.id);
  return null;
}

/** 試験だけ：カードの種類ごとに仮押さえ → 確定／取り消しを試し、手数料を返す（試験の鍵のときだけ動く） */
export async function selftest() {
  if (!test) throw new Error("selftest is test-mode only");
  const out: Record<string, unknown>[] = [];
  for (const brand of ["visa", "mastercard", "jcb", "amex"]) {
    const row: Record<string, unknown> = { brand };
    try {
      const mk = () => api("POST", "payment_intents", { amount: AMOUNT, currency: "jpy", capture_method: "manual", confirm: "true",
        payment_method: `pm_card_${brand}`, payment_method_types: { 0: "card" }, description: `selftest ${brand}` });
      const a = await mk();
      row.held = a.status;
      const c = await api("POST", `payment_intents/${a.id}/capture`, {});
      row.captured = c.status;
      const ch = await api("GET", `charges/${c.latest_charge}?expand[]=balance_transaction`);
      row.fee_on_capture = ch.balance_transaction?.fee;
      const b = await mk();
      const x = await api("POST", `payment_intents/${b.id}/cancel`, {});
      row.canceled = x.status;
      // 取り消したとき、売上（balance_transaction）と手数料が出ていないか
      if (x.latest_charge) {
        const xc = await api("GET", `charges/${x.latest_charge}?expand[]=balance_transaction`);
        row.cancel_charge = { captured: xc.captured, amount_captured: xc.amount_captured, fee: xc.balance_transaction?.fee ?? 0 };
      }
    } catch (e) {
      row.error = String(e).slice(0, 200);
    }
    out.push(row);
  }
  return out;
}

/** 試験だけ：クーポン（100%割引・1回の申し込みだけ・全体で5回・2027-01-21 まで）とコードを作る。もうあれば作らない */
export async function testCoupon(code: string) {
  if (!test) throw new Error("testCoupon is test-mode only");
  const found = await api("GET", `promotion_codes?code=${encodeURIComponent(code)}&limit=1`);
  if (found.data?.length) return { code, created: false, active: found.data[0].active };
  const until = Math.floor(Date.parse("2027-01-21T23:59:59+09:00") / 1000);
  const c = await api("POST", "coupons", { percent_off: 100, duration: "once", max_redemptions: 5, redeem_by: until, name: code });
  const base = { code, max_redemptions: 5, expires_at: until };
  // 新しい API の版では coupon の代わりに promotion[type]・promotion[coupon] で渡す
  const p = await api("POST", "promotion_codes", { ...base, coupon: c.id })
    .catch(() => api("POST", "promotion_codes", { ...base, promotion: { type: "coupon", coupon: c.id } }));
  return { code: p.code, created: true, active: p.active };
}

/** 試験だけ：支払い画面を通さずに、試験のカードで仮押さえを1つ作る（支払い画面を開けない環境での通しの試験用） */
export async function testHold(number: string): Promise<string> {
  if (!test) throw new Error("testHold is test-mode only");
  const pi = await api("POST", "payment_intents", { amount: AMOUNT, currency: "jpy", capture_method: "manual", confirm: "true",
    payment_method: "pm_card_visa", payment_method_types: { 0: "card" }, description: `イベント掲載 ${number}（試験）`,
    metadata: { number } });
  if (pi.status !== "requires_capture") throw new Error(`hold ${pi.status}`);
  return String(pi.id);
}
