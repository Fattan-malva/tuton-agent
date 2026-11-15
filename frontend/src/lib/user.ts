/** Nama tampil akun dari objek user Clerk; fallback konsisten di semua tempat. */
export function displayName(user: {
  fullName?: string | null
  username?: string | null
  primaryEmailAddress?: { emailAddress?: string | null } | null
} | null | undefined): string {
  return (
    user?.fullName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    'Akun'
  )
}

/** Inisial untuk avatar dari satu nama; dipakai konsisten di header/sidebar/akun. */
export function initials(nama: string): string {
  const kata = nama.trim().split(/\s+/).filter(Boolean)
  if (!kata.length) return 'TA'
  const huruf =
    kata.length > 1 ? kata[0][0] + kata[kata.length - 1][0] : kata[0].slice(0, 2)
  return huruf.toUpperCase()
}
