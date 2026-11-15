create table if not exists public.user_templates (
  user_id text not null,
  id text not null,
  name text not null,
  description text not null default '',
  schema jsonb not null default '{}'::jsonb,
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, id)
);
alter table public.user_templates enable row level security;
revoke all on public.user_templates from anon, authenticated;
drop trigger if exists user_templates_touch on public.user_templates;
create trigger user_templates_touch before update on public.user_templates for each row execute function public.tuton_touch_updated_at();
create unique index if not exists user_templates_one_default on public.user_templates(user_id) where is_default;
