-- ============================================================================
-- 한냥 (Hannyang) Supabase PostgreSQL 테이블 스키마 및 RLS 정책
-- 실행 위치: Supabase Dashboard (https://supabase.com/dashboard) -> SQL Editor -> New Query
-- ============================================================================

create table if not exists public.hannyang_debates (
  id uuid default gen_random_uuid() primary key,
  preset_id text,
  source_url text not null,
  issue_title text not null,
  total_comments integer not null default 0,
  filtered_curse_count integer not null default 0,
  pro_ratio integer not null default 50,
  con_ratio integer not null default 50,
  toxicity_before numeric(5,2) not null default 0.0,
  toxicity_after numeric(5,2) not null default 0.0,
  debate_script jsonb not null default '[]'::jsonb,
  detox_samples jsonb not null default '[]'::jsonb,
  video_url text,
  engine_mode text default 'YOUTUBE_GEMINI_LIVE',
  created_at timestamptz default now()
);

-- 브라우저에서 Publishable Key (sb_publishable_...)로 즉시 조회 및 저장 가능하도록 RLS 정책 허용
alter table public.hannyang_debates enable row level security;

drop policy if exists "Allow public read hannyang_debates" on public.hannyang_debates;
create policy "Allow public read hannyang_debates"
  on public.hannyang_debates for select
  to anon, authenticated
  using (true);

drop policy if exists "Allow public insert hannyang_debates" on public.hannyang_debates;
create policy "Allow public insert hannyang_debates"
  on public.hannyang_debates for insert
  to anon, authenticated
  with check (true);
