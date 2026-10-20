-- おでかけの表の Data API の権限をはっきり書く（2026-10-20）。
-- Supabase は 2026-10-30 から、public に新しく作る表へ Data API の権限（anon・authenticated・service_role への GRANT）を
-- 自動では付けなくなる。db reset・preview branch でも同じなので、表を作るマイグレーションには必要な GRANT を書く。
-- 使い方：
--   ・サイトから直接は読み書きしない（書き込みは Edge Function odekake-form が service_role で行う）→ anon には何も与えない
--   ・運営（is_admin）はログインして読む・直す → authenticated に select・update（行は RLS の is_admin で絞る）
--   ・送り過ぎの記録と設定（合言葉）は service_role だけ
revoke all on public.odekake_inquiries, public.odekake_submissions, public.odekake_form_hits, public.odekake_settings
  from anon, authenticated;
grant select, insert, update, delete on public.odekake_inquiries, public.odekake_submissions,
  public.odekake_form_hits, public.odekake_settings to service_role;
grant select, update on public.odekake_inquiries, public.odekake_submissions to authenticated;
