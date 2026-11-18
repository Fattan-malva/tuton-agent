-- Skill custom per akun. SKILL.md bawaan tetap berasal dari image/repo;
-- baris ini hanya menyimpan override user dan pilihan default.
create table if not exists public.user_skills (
  user_id text not null,
  name text not null,
  content text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, name)
);
alter table public.user_skills enable row level security;
revoke all on public.user_skills from anon, authenticated;
drop trigger if exists user_skills_touch on public.user_skills;
create trigger user_skills_touch before update on public.user_skills for each row execute function public.tuton_touch_updated_at();

alter table public.user_identities
  add column if not exists skill_default text not null default 'naskah-id';
comment on column public.user_identities.skill_default is
  'ID skill default akun; skill bawaan tidak disimpan di tabel.';
