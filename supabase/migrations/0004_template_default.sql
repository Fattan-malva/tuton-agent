-- ============================================================================
--  Tuton Agent - template default per akun
-- ============================================================================
--  Jalankan SEKALI di Supabase Dashboard -> SQL Editor, SEBELUM deploy kode
--  yang membacanya.
--
--  Default dulu disimpan di `user_templates.is_default`, sehingga template
--  bawaan tidak bisa dijadikan default (tidak punya baris) dan kolom uniknya
--  menolak pindah default. Sekarang pilihannya satu kolom di profil.
-- ============================================================================

alter table public.user_identities
  add column if not exists template_default text not null default '';

comment on column public.user_identities.template_default is
  'ID template jawaban default akun ini (bawaan atau milik user).';

-- Bawa pilihan lama supaya user tidak kembali ke template bawaan.
update public.user_identities u
set template_default = t.id
from public.user_templates t
where t.user_id = u.user_id and t.is_default and u.template_default = '';
