-- イベント掲載の仮押さえと、自動の受付メール（2026-10-20 代表）。
-- 申し込みの流れ（status）：
--   pending_payment（フォームを送り、Stripe の支払い画面へ）
--   → authorized（仮押さえ済み。ここで受付メール。ダッシュボードの「判断待ち」に出す）
--   → approve（代表が「受ける」）→ captured（毎朝の処理で確定。掲載決定のメール）
--   → reject（代表が「受けない」）→ canceled（毎朝の処理で取り消し。お断りのメール）
--   → expired（仮押さえの期限の前に取り消し。期限切れのメール）
--   abandoned：支払い画面で止めた・戻らなかった（仮押さえ無し。メールも送らない）
alter table public.odekake_submissions drop constraint if exists odekake_submissions_status_check;
alter table public.odekake_submissions add constraint odekake_submissions_status_check
  check (status in ('open','pending_payment','authorized','approve','reject','captured','canceled','expired','abandoned',
                    'approved','paid','published','declined','done'));
alter table public.odekake_submissions
  add column if not exists stripe_session text,
  add column if not exists payment_intent text,
  add column if not exists authorized_at timestamptz,
  add column if not exists decided_at timestamptz,
  add column if not exists mail_sent_at timestamptz,      -- 受付メール
  add column if not exists result_mail_at timestamptz;    -- 確定・取り消し・期限切れのメール
alter table public.odekake_inquiries
  add column if not exists mail_sent_at timestamptz;

-- 毎朝の作業だけが受付の process を呼べるようにする合言葉（運営だけが読める。新しい鍵を増やさないため）
create table if not exists public.odekake_settings (key text primary key, value text not null);
alter table public.odekake_settings enable row level security;
create policy odekake_settings_admin on public.odekake_settings for all using (is_admin()) with check (is_admin());
insert into public.odekake_settings (key, value) values ('process_token', encode(gen_random_bytes(24), 'hex'))
on conflict (key) do nothing;
