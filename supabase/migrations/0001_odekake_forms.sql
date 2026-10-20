-- 2026-10-20 に Supabase（fukui-ekimae のプロジェクト）へ適用済み。記録として置く。
-- おでかけ（福井・石川）の問い合わせと、イベント掲載の申し込み（代表 B 案）。
-- 書き込みは Edge Function odekake-form（service role）だけ。サイトから直接は書けない・読めない。
-- 読むのは運営（is_admin）と、毎朝の作業（ダッシュボードの「判断待ち」に出す）。
create table public.odekake_inquiries (
  id          uuid primary key default gen_random_uuid(),
  region      text not null check (region in ('fukui','ishikawa')),
  kind        text not null check (kind in ('fix','remove','paid','other')),
  name        text not null check (char_length(name) between 1 and 100),
  email       text not null check (char_length(email) between 3 and 200),
  page        text not null default '' check (char_length(page) <= 300),
  message     text not null check (char_length(message) between 1 and 1000),
  status      text not null default 'open' check (status in ('open','done')),
  created_at  timestamptz not null default now()
);

create table public.odekake_submissions (
  id            uuid primary key default gen_random_uuid(),
  number        text unique not null,           -- 申込番号（決済リンクの client_reference_id にも使う）
  region        text not null check (region in ('fukui','ishikawa')),
  event_name    text not null check (char_length(event_name) between 1 and 100),
  date_from     date not null,
  date_to       date,
  time_text     text not null default '' check (char_length(time_text) <= 100),
  venue         text not null check (char_length(venue) between 1 and 100),
  city          text not null check (char_length(city) between 1 and 30),
  address       text not null default '' check (char_length(address) <= 200),
  fee           text not null default '' check (char_length(fee) <= 100),
  body          text not null check (char_length(body) between 1 and 300),
  target        text not null default '' check (char_length(target) <= 300),
  organizer     text not null check (char_length(organizer) between 1 and 100),
  official_url  text not null check (char_length(official_url) between 8 and 300),
  wish_from     date,
  wish_to       date,
  contact_name  text not null check (char_length(contact_name) between 1 and 100),
  contact_email text not null check (char_length(contact_email) between 3 and 200),
  flyer_path    text,                            -- 非公開の置き場 odekake-flyers の中の場所
  flyer_type    text,
  status        text not null default 'open' check (status in ('open','approved','paid','published','declined','done')),
  created_at    timestamptz not null default now()
);

-- 送り過ぎを止めるための記録（IP は生で持たず、ハッシュだけ）
create table public.odekake_form_hits (
  ip_hash    text not null,
  created_at timestamptz not null default now()
);
create index odekake_form_hits_idx on public.odekake_form_hits (ip_hash, created_at);

alter table public.odekake_inquiries   enable row level security;
alter table public.odekake_submissions enable row level security;
alter table public.odekake_form_hits   enable row level security;
create policy odekake_inq_admin on public.odekake_inquiries   for all using (is_admin()) with check (is_admin());
create policy odekake_sub_admin on public.odekake_submissions for all using (is_admin()) with check (is_admin());
-- odekake_form_hits は service role だけ（ポリシーなし＝ほかは読めない・書けない）

-- チラシの置き場（非公開。公開 URL を作らない）。5MB まで、画像と PDF だけ
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('odekake-flyers', 'odekake-flyers', false, 5242880, array['image/jpeg','image/png','image/webp','application/pdf'])
on conflict (id) do nothing;
create policy odekake_flyers_admin on storage.objects for select
  using (bucket_id = 'odekake-flyers' and public.is_admin());
