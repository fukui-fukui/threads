// おでかけ（福井・石川）の問い合わせと、イベント掲載の申し込みを受け取る（2026-10-20 代表 B 案）。
// サイトのフォームから multipart/form-data で呼ばれる。ログイン不要（verify_jwt なし）なので、ここで確かめる：
//   ・送ってよいサイトか（Origin）
//   ・ロボットよけ（Cloudflare Turnstile。秘密鍵 TURNSTILE_SECRET が登録されていれば必ず確かめる）
//   ・人には見えない欄（website）が空か、開いてから3秒以上たっているか
//   ・同じところから1時間に5件まで
//   ・文字数・日付・URL・メールの形
//   ・チラシ：5MB まで、JPEG / PNG / WebP / PDF だけ。拡張子でなく中身の先頭の印で確かめ、非公開の置き場へ
// 掲載の申し込みは、SUBMISSION_OPEN が true のときだけ受け付ける（2026-10-20 代表：特商法の表記と決済リンクがそろったので開く。
// 止めるときは false にして載せ直す）。
// PAY_HOLD が true のとき、申し込みはその場で Stripe の支払い画面（カードの仮押さえ）へ移す（pay.ts）。
// 受付・確定・取り消し・期限切れのメールは mail.ts。
//   type=confirm：支払い画面から戻ったとき。Stripe に問い合わせて仮押さえを確かめ、受付メールを送る
//   type=process：毎朝の作業から呼ぶ。代表の「受ける／受けない」の確定・取り消し、戻らなかった人の確認、期限切れ
import { createClient } from "jsr:@supabase/supabase-js@2";
import * as mail from "./mail.ts";
import * as pay from "./pay.ts";

const ORIGINS = ["https://odekake.fukui-fukui.com", "https://ishikawa-odekake.fukui-fukui.com"];
const REGION_OF: Record<string, string> = { [ORIGINS[0]]: "fukui", [ORIGINS[1]]: "ishikawa" };
const MAX_FILE = 5 * 1024 * 1024;
const PER_HOUR = 5;
const SUBMISSION_OPEN = true;
const PAY_HOLD = true;

function cors(origin: string) {
  return {
    "Access-Control-Allow-Origin": ORIGINS.includes(origin) ? origin : ORIGINS[0],
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Vary": "Origin",
  };
}

function reply(origin: string, status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), { status, headers: { ...cors(origin), "Content-Type": "application/json" } });
}

export function fileKind(head: Uint8Array): string | null {
  const b = (i: number) => head[i];
  if (b(0) === 0xff && b(1) === 0xd8 && b(2) === 0xff) return "image/jpeg";
  if (b(0) === 0x89 && b(1) === 0x50 && b(2) === 0x4e && b(3) === 0x47) return "image/png";
  if (b(0) === 0x52 && b(1) === 0x49 && b(2) === 0x46 && b(3) === 0x46 && b(8) === 0x57 && b(9) === 0x45 && b(10) === 0x42 && b(11) === 0x50) return "image/webp";
  if (b(0) === 0x25 && b(1) === 0x50 && b(2) === 0x44 && b(3) === 0x46) return "application/pdf";
  return null;
}

const EXT: Record<string, string> = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf" };
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

type Field = { max: number; min?: number; re?: RegExp };
export const INQUIRY: Record<string, Field> = {
  kind: { max: 10, min: 1, re: /^(fix|remove|paid|other)$/ },
  name: { max: 100, min: 1 },
  email: { max: 200, min: 3, re: EMAIL },
  page: { max: 300 },
  message: { max: 1000, min: 1 },
};
export const SUBMISSION: Record<string, Field> = {
  event_name: { max: 100, min: 1 },
  date_from: { max: 10, min: 10, re: DATE },
  date_to: { max: 10, re: /^(\d{4}-\d{2}-\d{2})?$/ },
  time_text: { max: 100 },
  venue: { max: 100, min: 1 },
  city: { max: 30, min: 1 },
  address: { max: 200 },
  fee: { max: 100 },
  body: { max: 300, min: 1 },
  target: { max: 300 },
  organizer: { max: 100, min: 1 },
  official_url: { max: 300, min: 8, re: /^https?:\/\/\S+$/ },
  wish_from: { max: 10, re: /^(\d{4}-\d{2}-\d{2})?$/ },
  wish_to: { max: 10, re: /^(\d{4}-\d{2}-\d{2})?$/ },
  contact_name: { max: 100, min: 1 },
  contact_email: { max: 200, min: 3, re: EMAIL },
};

/** 欄を読み、決まりに合わなければその欄の名前を返す */
export function check(form: FormData, rules: Record<string, Field>): { row: Record<string, string | null>; bad: string | null } {
  const row: Record<string, string | null> = {};
  for (const [k, r] of Object.entries(rules)) {
    const v = String(form.get(k) ?? "").trim();
    if (v.length > r.max || v.length < (r.min ?? 0) || (r.re && !r.re.test(v))) return { row, bad: k };
    row[k] = v === "" && !r.min ? (k.startsWith("date_") || k.startsWith("wish_") ? null : "") : v;
  }
  // 本文の URL は3本まで（宣伝の書き込みよけ）
  const text = Object.values(row).join(" ");
  if ((text.match(/https?:\/\//g) ?? []).length > 4) return { row, bad: "url" };
  return { row, bad: null };
}

async function sha256(s: string) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(d)).map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function turnstileOk(secret: string, token: string, ip: string) {
  const body = new FormData();
  body.append("secret", secret);
  body.append("response", token);
  if (ip) body.append("remoteip", ip);
  const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body });
  const j = await r.json().catch(() => ({}));
  return j.success === true;
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin") ?? "";
  if (req.method === "OPTIONS") return new Response(null, { headers: cors(origin) });
  if (req.method !== "POST") return reply(origin, 405, { error: "method" });
  if (!ORIGINS.includes(origin)) return reply(origin, 403, { error: "origin" });
  const region = REGION_OF[origin];

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return reply(origin, 400, { error: "form" });
  }
  const type = String(form.get("type") ?? "");
  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  if (type === "confirm") return reply(origin, 200, await confirm(db, String(form.get("n") ?? ""), String(form.get("s") ?? "")));
  if (type === "process") {
    // 毎朝の作業だけが呼べるように、運営だけが読める表の合言葉と照らす（新しい鍵を増やさないため）
    const { data: t } = await db.from("odekake_settings").select("value").eq("key", "process_token").maybeSingle();
    if (!t?.value || String(form.get("token") ?? "") !== t.value) return reply(origin, 403, { error: "token" });
    return reply(origin, 200, await process(db));
  }
  if (type !== "inquiry" && type !== "submission") return reply(origin, 400, { error: "type" });
  if (type === "submission" && !SUBMISSION_OPEN) return reply(origin, 403, { error: "closed" });

  // 人には見えない欄・開いてからの時間（ロボットは即座に全部埋める）
  if (String(form.get("website") ?? "") !== "") return reply(origin, 200, { ok: true });
  const opened = Number(form.get("opened") ?? 0);
  if (!opened || Date.now() - opened < 3000) return reply(origin, 400, { error: "fast" });
  if (form.get("agree") !== "1" || (type === "submission" && form.get("agree_flyer") !== "1")) {
    return reply(origin, 400, { error: "agree" });
  }

  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
  const secret = Deno.env.get("TURNSTILE_SECRET") ?? "";
  if (secret && !(await turnstileOk(secret, String(form.get("cf-turnstile-response") ?? ""), ip))) {
    return reply(origin, 400, { error: "robot" });
  }

  const ipHash = await sha256(`${ip}|${Deno.env.get("SUPABASE_URL")}|odekake-form`);
  const since = new Date(Date.now() - 3600_000).toISOString();
  const { count } = await db.from("odekake_form_hits").select("*", { count: "exact", head: true })
    .eq("ip_hash", ipHash).gte("created_at", since);
  if ((count ?? 0) >= PER_HOUR) return reply(origin, 429, { error: "many" });
  await db.from("odekake_form_hits").insert({ ip_hash: ipHash });

  if (type === "inquiry") {
    const { row, bad } = check(form, INQUIRY);
    if (bad) return reply(origin, 400, { error: "field", field: bad });
    const { data: saved, error } = await db.from("odekake_inquiries").insert({ ...row, region }).select().single();
    if (error) return reply(origin, 500, { error: "save" });
    if (await mail.send(mail.inquiryReceived(saved))) {
      await db.from("odekake_inquiries").update({ mail_sent_at: new Date().toISOString() }).eq("id", saved.id);
    }
    return reply(origin, 200, { ok: true });
  }

  const { row, bad } = check(form, SUBMISSION);
  if (bad) return reply(origin, 400, { error: "field", field: bad });
  const number = `S${new Date().toISOString().slice(2, 10).replaceAll("-", "")}-${crypto.randomUUID().slice(0, 6).toUpperCase()}`;
  let flyer_path: string | null = null;
  let flyer_type: string | null = null;
  const file = form.get("flyer");
  if (file instanceof File && file.size > 0) {
    if (file.size > MAX_FILE) return reply(origin, 400, { error: "field", field: "flyer" });
    const bytes = new Uint8Array(await file.arrayBuffer());
    flyer_type = fileKind(bytes.slice(0, 16));
    if (!flyer_type) return reply(origin, 400, { error: "field", field: "flyer" });
    flyer_path = `${region}/${number}.${EXT[flyer_type]}`;
    const up = await db.storage.from("odekake-flyers").upload(flyer_path, bytes, { contentType: flyer_type });
    if (up.error) return reply(origin, 500, { error: "save" });
  }
  const status = PAY_HOLD ? "pending_payment" : "open";
  const { error } = await db.from("odekake_submissions").insert({ ...row, region, number, flyer_path, flyer_type, status });
  if (error) return reply(origin, 500, { error: "save" });
  if (!PAY_HOLD) return reply(origin, 200, { ok: true, number });
  try {
    const site = mail.SITES[region];
    const s = await pay.createCheckout(pay.checkoutBody({ number, region, siteName: site.name, siteUrl: site.url,
      email: String(row.contact_email), eventName: String(row.event_name) }));
    await db.from("odekake_submissions").update({ stripe_session: s.id }).eq("number", number);
    return reply(origin, 200, { ok: true, number, pay_url: s.url });
  } catch (e) {
    console.error(e);
    await db.from("odekake_submissions").update({ status: "abandoned" }).eq("number", number);
    return reply(origin, 500, { error: "pay" });
  }
});

type DB = ReturnType<typeof createClient>;
const now = () => new Date().toISOString();

/** 仮押さえが済んでいれば authorized にして受付メールを送る。済んでいなければ何もしない */
async function settle(db: DB, r: Record<string, unknown>): Promise<string> {
  if (!r.stripe_session) return String(r.status);
  const s = await pay.getSession(String(r.stripe_session));
  const pi = pay.heldIntent(s, String(r.number));
  if (pi) {
    await db.from("odekake_submissions").update({ status: "authorized", payment_intent: pi, authorized_at: now() })
      .eq("number", r.number).eq("status", "pending_payment");
    if (!r.mail_sent_at && await mail.send(mail.submissionReceived({ ...r, status: "authorized" }))) {
      await db.from("odekake_submissions").update({ mail_sent_at: now() }).eq("number", r.number);
    }
    return "authorized";
  }
  if (s.status === "expired") {
    await db.from("odekake_submissions").update({ status: "abandoned" }).eq("number", r.number).eq("status", "pending_payment");
    return "abandoned";
  }
  return String(r.status);
}

/** 支払い画面から戻ったとき */
async function confirm(db: DB, number: string, session: string) {
  if (!/^S\d{6}-[0-9A-F]{6}$/.test(number)) return { error: "number" };
  const { data: r } = await db.from("odekake_submissions").select("*").eq("number", number).maybeSingle();
  if (!r || (session && r.stripe_session !== session)) return { error: "number" };
  if (r.status !== "pending_payment") return { ok: r.status === "authorized" || r.status === "approve", number, status: r.status };
  try {
    const st = await settle(db, r);
    return { ok: st === "authorized", number, status: st };
  } catch (e) {
    console.error(e);
    return { error: "pay" };
  }
}

/** 毎朝の作業から呼ぶ。代表の答え（approve / reject）を Stripe に反映し、メールを送る */
async function process(db: DB) {
  const out: Record<string, string[]> = { authorized: [], captured: [], canceled: [], expired: [], abandoned: [], soon: [], errors: [] };
  const { data: rows } = await db.from("odekake_submissions").select("*")
    .in("status", ["pending_payment", "authorized", "approve", "reject"]);
  for (const r of rows ?? []) {
    const n = String(r.number);
    try {
      if (r.status === "pending_payment") {
        const st = await settle(db, r);
        if (st === "authorized" || st === "abandoned") out[st].push(n);
      } else if (r.status === "approve" && r.payment_intent) {
        await pay.capture(String(r.payment_intent));
        await db.from("odekake_submissions").update({ status: "captured", decided_at: now() }).eq("number", n);
        if (await mail.send(mail.submissionCaptured(r))) await db.from("odekake_submissions").update({ result_mail_at: now() }).eq("number", n);
        out.captured.push(n);
      } else if (r.status === "reject" && r.payment_intent) {
        await pay.cancel(String(r.payment_intent));
        await db.from("odekake_submissions").update({ status: "canceled", decided_at: now() }).eq("number", n);
        if (await mail.send(mail.submissionCanceled(r))) await db.from("odekake_submissions").update({ result_mail_at: now() }).eq("number", n);
        out.canceled.push(n);
      } else if (r.status === "authorized" && r.authorized_at) {
        const age = Date.now() - new Date(String(r.authorized_at)).getTime();
        if (age > pay.HOLD_LIMIT_MS) {
          await pay.cancel(String(r.payment_intent));
          await db.from("odekake_submissions").update({ status: "expired", decided_at: now() }).eq("number", n);
          if (await mail.send(mail.submissionExpired(r))) await db.from("odekake_submissions").update({ result_mail_at: now() }).eq("number", n);
          out.expired.push(n);
        } else if (age > pay.REMIND_MS) out.soon.push(n);
      }
    } catch (e) {
      console.error(n, e);
      out.errors.push(`${n}: ${String(e).slice(0, 120)}`);
    }
  }
  let acct = "";
  try { const a = await pay.account(); acct = `${a.id}${a.livemode === false ? "（試験）" : ""}`; } catch (_) { acct = "読めない"; }
  return { ok: true, account: acct, mode: Deno.env.get("STRIPE_MODE") === "test" ? "test" : "live", ...out };
  // 申込番号の一覧は、運営だけが読める表にもあるので、ここで返してもよい（呼べるのは合言葉を知る毎朝の作業だけ）
}
