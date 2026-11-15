-- ============================================================================
--  Tuton Agent - profil per akun Clerk
-- ============================================================================
--  Jalankan SEKALI di Supabase Dashboard -> SQL Editor.
--
--  Isi: satu baris per user Clerk. Cookie Moodle dan identitas mahasiswa
--  disimpan di sini karena berbeda per akun; server Python mengaksesnya
--  memakai service key (bukan anon key), jadi RLS ditutup total untuk anon.
--
--  Catatan keamanan: cookie Moodle adalah kredensial hidup. Jangan pernah
--  membuka policy SELECT untuk `anon`/`authenticated` di tabel ini.
-- ============================================================================

create table if not exists public.user_identities (
  user_id        text primary key,
  email          text not null default '',
  name           text not null default '',

  -- Identitas untuk kop DOCX.
  nama           text not null default '',
  nim            text not null default '',
  semester       text not null default '',
  ut_daerah      text not null default '',
  prodi          text not null default '',

  -- Cookie MoodleSession milik akun ini (nilai mentah, tanpa nama cookie).
  cookie_moodle  text not null default '',

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

comment on table public.user_identities is
  'Profil per user Clerk: identitas DOCX dan cookie Moodle. Hanya service key yang boleh membaca.';

create index if not exists user_identities_updated_at_idx
  on public.user_identities (updated_at desc);

alter table public.user_identities enable row level security;

-- Tidak ada policy sama sekali: anon key dan JWT user tidak bisa membaca,
-- menulis, atau menghapus. Server memakai service key yang melewati RLS.
revoke all on public.user_identities from anon, authenticated;

-- Trigger updated_at supaya baris yang di-upsert tanpa kolom itu tetap akurat.
create or replace function public.tuton_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists user_identities_touch on public.user_identities;
create trigger user_identities_touch
  before update on public.user_identities
  for each row execute function public.tuton_touch_updated_at();

-- Keepalive ringan: satu baris penanda aktivitas yang tidak menyimpan data
-- pengguna. Dibaca/tulis oleh thread keepalive supaya project tidak
-- di-pause setelah 7 hari tanpa aktivitas.
create table if not exists public.tuton_keepalive (
  id          int primary key,
  terakhir    timestamptz not null default now(),
  catatan     text not null default ''
);

insert into public.tuton_keepalive (id, catatan)
values (1, 'heartbeat tuton-agent')
on conflict (id) do nothing;

alter table public.tuton_keepalive enable row level security;
revoke all on public.tuton_keepalive from anon, authenticated;
