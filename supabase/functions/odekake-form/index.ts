// おでかけ（福井・石川）の問い合わせと、イベント掲載の申し込みを受け取る（2026-10-20 代表 B 案）。
// サイトのフォームから multipart/form-data で呼ばれる。ログイン不要（verify_jwt なし）なので、ここで確かめる：
//   ・送ってよいサイトか（Origin）
//   ・ロボットよけ（Cloudflare Turnstile。秘密鍵 TURNSTILE_SECRET が登録されていれば必ず確かめる）
//   ・人には見えない欄（website）が空か、開いてから3秒以上たっているか
//   ・同じところから1時間に5件まで
//   ・文字数・日付・URL・メールの形
//   ・チラシ：5MB まで、JPEG / PNG / WebP / PDF だけ。拡張子でなく中身の先頭の印で確かめ、非公開の置き場へ
// 掲載の申し込みは、SUBMISSION_OPEN=1 になるまで受け付けない（特商法の表記が決まってから公開。代表 10/20）。
import { createClient } from "jsr:@supabase/supabase-js@2";

const ORIGINS = ["https://odekake.fukui-fukui.com", "https://ishikawa-odekake.fukui-fukui.com"];
const REGION_OF: Record<string, string> = { [ORIGINS[0]]: "fukui", [ORIGINS[1]]: "ishikawa" };
const MAX_FILE = 5 * 1024 * 1024;
const PER_HOUR = 5;

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
  if (type !== "inquiry" && type !== "submission") return reply(origin, 400, { error: "type" });
  if (type === "submission" && Deno.env.get("SUBMISSION_OPEN") !== "1") return reply(origin, 403, { error: "closed" });

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

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const ipHash = await sha256(`${ip}|${Deno.env.get("SUPABASE_URL")}|odekake-form`);
  const since = new Date(Date.now() - 3600_000).toISOString();
  const { count } = await db.from("odekake_form_hits").select("*", { count: "exact", head: true })
    .eq("ip_hash", ipHash).gte("created_at", since);
  if ((count ?? 0) >= PER_HOUR) return reply(origin, 429, { error: "many" });
  await db.from("odekake_form_hits").insert({ ip_hash: ipHash });

  if (type === "inquiry") {
    const { row, bad } = check(form, INQUIRY);
    if (bad) return reply(origin, 400, { error: "field", field: bad });
    const { error } = await db.from("odekake_inquiries").insert({ ...row, region });
    if (error) return reply(origin, 500, { error: "save" });
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
  const { error } = await db.from("odekake_submissions").insert({ ...row, region, number, flyer_path, flyer_type });
  if (error) return reply(origin, 500, { error: "save" });
  return reply(origin, 200, { ok: true, number });
});
