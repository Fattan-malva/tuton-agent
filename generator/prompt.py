from __future__ import annotations

import json
from pathlib import Path

from config import Config


def build_prompt(
    *,
    work_kind: str,  # "diskusi" | "tugas"
    index: int,
    course_name: str,
    section_num: int,
    activity_title: str,
    soal_path: Path,
    attachment_dir: Path,
    jawaban_path: Path,
) -> str:
    """Instruksi untuk opencode run (agent tuton)."""
    ident = {
        "Nama": Config.NAMA,
        "NIM": Config.NIM,
        "Prodi": Config.PRODI,
    }
    lampiran = [
        p.name
        for p in sorted(attachment_dir.glob("*"), key=lambda p: p.name)
        if p.is_file()
    ]

    lines = [
        f"Kamu adalah asisten pengerjaan {work_kind} tutorial online (tuton).",
        "Selesaikan pertanyaan yang ada di file soal, lalu TULIS jawaban final ke path yang ditentukan.",
        "",
        "## Konteks",
        f"- Jenis pekerjaan: {work_kind} ke-{index}",
        f"- Mata kuliah: {course_name}",
        f"- Sesi: {section_num}",
        f"- Judul aktivitas: {activity_title}",
        f"- Identitas mahasiswa: {json.dumps(ident, ensure_ascii=False)}",
        "",
        "## Bahan",
        f"- Soal: baca file `{soal_path}`. Seluruh isi lampiran (gambar, PDF, Excel, dokumen) "
        "SUDAH diekstrak ke file tersebut pada bagian 'Isi lampiran ... (transkripsi)'.",
        f"- DILARANG membuka/membaca file di folder lampiran `{attachment_dir}`. "
        "Model ini tidak melihat file biner, dan jangan coba verifikasi lewat alat lain.",
    ]
    if lampiran:
        lines.append(f"  Isi folder: {', '.join(lampiran)}")
    lines.extend(
        [
            f"- Gaya jawaban yang diharapkan (mengikuti contoh jawaban asli mahasiswa): langsung ke inti, "
            "kalimat jelas, untuk soal hitungan tulis langkah penyelesaian berurutan (Diketahui/ditanya → "
            "penyelesaian → kesimpulan), gunakan sub-bagian a/b/c sesuai butir soal, bahasa formal tapi natural.",
            "- Semua perhitungan/rumus yang memuat simbol dan angka tulis di baris tersendiri dibungkus "
            "$$ ... $$ (hanya satu persamaan per baris), misal:",
            "  $$ 2A = [[4, 2], [0, 6]] $$",
            "  $$ AB = [[0, 13], [-6, 15]] $$",
            "  Notasi yang didukung untuk dikonversi jadi equation Word: matriks [[a, b], [c, d]], "
            "pangkat x^2, akar sqrt(...), operator + - × = .",
            "",
            "## Aturan kejujuran (WAJIB)",
            "- JANGAN mengarang sumber, tautan, nomor halaman, ISBN, DOI, atau nama penulis. "
            "Referensi yang tidak dapat diverifikasi HARUS dibuang, bukan ditebak.",
            "- JANGAN mengklaim sudah membaca dokumen yang tidak kamu akses. Kalau memang tidak "
            "bisa diakses, nyatakan apa yang tidak diketahui secara eksplisit di bagian Catatan/Asumsi.",
            "- Jangan menulis placeholder, TODO, 'dst.', atau contoh angka yang tidak berasal dari soal.",
            "- Jika satu butir benar-benar mustahil dijawab dari bahan yang ada, tulis jawaban "
            "separtial yang jujur beserta alasannya — jangan mengarang angka.",
            "",
            "## Cara kerja (WAJIB, ikuti berurutan)",
            "LANGKAH 1 — PETA SOAL. Baca file soal dari atas sampai bawah, lalu buat daftar "
            "internal semua pertanyaan/butir yang harus dijawab (nomor butir, mis. 1, 2, a, b, c, "
            "i-iv). Jangan tulis peta ini ke file jawaban; ini hanya catatan internal kamu.",
            "",
            "LANGKAH 2 — RISET SUMBER. Sebelum menjawab, kumpulkan sumber nyata yang kredibel "
            "dan bisa diakses publik untuk topik ini. Gunakan tool websearch untuk mencari, lalu "
            "webfetch untuk MEMERIKSA setiap kandidat satu per satu. Utamakan sumber berikut, "
            "berurutan dari yang paling tepercaya:",
            "  1. Buku teks: cari edisi yang benar via Google Books atau Open Library, "
            "verifikasi judul + penulis + tahun + penerbit + ISBN.",
            "  2. Artikel jurnal peer-reviewed: verifikasi lewat Crossref "
            "(webfetch `https://api.crossref.org/works/<DOI>`) atau OpenAlex "
            "(webfetch `https://api.openalex.org/works?search=...`). Hanya DOI yang benar-benar "
            "mengembalikan metadata yang boleh dipakai.",
            "  3. Standar/norma resmi yang gratis: ISO, IEEE, IETF, W3C, WHO, NIST, "
            "dokumentasi resmi (python.org, docs.python.org, nodejs.org, postgresql.org, "
            "w3.org, developer.mozilla.org).",
            "  4. Jurnal open access: DOAJ, PubMed/PMC, arXiv (periksa lewat "
            "webfetch `https://arxiv.org/abs/<id>`), dan repository institusi "
            "(mis. ETD UT, repositori.kemdikbud.go.id).",
            "  5. Sumber sekunder (blog, Stack Overflow, YouTube) HANYA sebagai konteks tambahan, "
            "dan kalau dipakai harus tetap diberi label sumber tidak resmi.",
            "Untuk SETIAP referensi yang mau dipakai, kamu WAJIB sudah menjalankan webfetch dan "
            "melihat responsnya. Referensi yang webfetch-nya gagal/404 TIDAK boleh masuk Daftar "
            "Pustaka. Kalau verifikasi gagal, cari yang lain; jangan menaksir.",
            "",
            "LANGKAH 3 — JAWAB. Jawab SETIAP butir dari peta langkah 1, tidak ada yang dilewati. "
            "Untuk setiap butir: (a) kerjakan langkahnya, (b) cek ulang hasil hitungannya secara "
            "independen (hitung ulang dengan cara lain, cek satuan, cek masuk akal terhadap "
            "besaran soal), (c) tulis jawaban akhirnya di bawah sub-bagian dengan label butir "
            "yang sama dengan soal (a/b/c atau 1/2/3).",
            "",
            "LANGKAH 4 — AUDIT SEBELUM MENULIS. Periksa daftar berikut satu per satu, dan perbaiki "
            "sebelum menulis file:",
            "  [ ] Semua butir soal punya bagian jawaban dengan label yang sama.",
            "  [ ] Tidak ada butir yang dijawab 'seperti di atas' atau 'dapat ditafsirkan begitu saja'.",
            "  [ ] Semua angka hasil hitung sudah dicek ulang; tidak ada yang bertentangan antar bagian.",
            "  [ ] Tidak ada kalimat yang setengah jadi atau terpotong.",
            "  [ ] Semua referensi di Daftar Pustaka sudah pernah diverifikasi via webfetch, "
            "dan tautan/DOI-nya benar-benar hidup.",
            "  [ ] Tidak ada karakter aneh (mis. huruf CJK/Cyrillic) yang nyasar di dalam kata "
            "Indonesia. Tulis ulang dari nol bila perlu — JANGAN melakukan edit kecil-kecil pada "
            "teks yang sudah rusak, karena itu menyisakan fragmen aneh.",
            "",
            "LANGKAH 5 — TULIS. Tulis jawaban final ke file dengan struktur di bawah. Tulis file "
            "sekali secara utuh. Jangan mengedit file berulang kali untuk 'memperbaiki' satu "
            "kata — itu pernah merusak jawaban (menyisakan fragmen acak).",
            "",
            "## Instruksi",
            f"1. Pahami soal yang tertulis di file `{soal_path}`. Kerjakan dengan benar dan LENGKAP, tidak melewatkan butir soal.",
            "2. JANGAN menjalankan perintah shell/bash apa pun. JANGAN membaca, memproses, atau meng-OCR file "
            "lampiran (gambar/PDF/Excel). JANGAN crop, resize, atau render ASCII. Semua isi lampiran sudah "
            "tersedia sebagai teks di dalam file soal.",
            "3. Jika teks soal benar-benar TIDAK ADA (file hanya berisi 'soal kosong / perlu dibaca dari "
            "lampiran' tanpa bagian 'Isi lampiran ... (transkripsi)' yang terbaca), maka JANGAN mengarang "
            "pertanyaan atau jawaban. Tulis di file jawaban: '## Jawab' lalu baris menjelaskan bahwa soal "
            "tidak ditemukan / tidak tersedia untuk dikerjakan, dan akhiri. Jangan menulis jawaban fiktif.",
            "   Jika teks soal ada tetapi sebagian '[tidak terbaca]', kerjakan dengan asumsi yang wajar dan "
            "cantumkan asumsinya di akhir jawaban.",
            "4. Jangan menulis ulang isi soal di jawaban. Cukup jawabannya.",
            "5. Sertakan 'Daftar Pustaka' di akhir jawaban yang BERISI HANYA referensi NYATA dan "
            "sudah diverifikasi lewat webfetch (lihat LANGKAH 2):",
            "   - Setiap entri harus bisa dibuka pembaca lain: sertakan tautan stabil (DOI resolver "
            "https://doi.org/..., URL penerbit/arxiv/repositori, atau ISBN untuk buku).",
            "   - Kalau sebuah buku tidak punya URL gratis, tetap tulis ISBN-nya agar bisa dicari "
            "pembaca; utamakan edisi yang kutipannya paling sering dipakai dan benar-benar Anda "
            "konfirmasi judul/penulis/tahunnya.",
            "   - Pilih 3-8 entri yang paling relevan dengan butir soal, bukan daftar panjang "
            "yang isinya cuma mengulang satu sama lain.",
            "   - Format APA edisi ke-7:",
            "     Buku  : Penulis, A. A., & Penulis, B. B. (Tahun). *Judul Buku* (edisi). Penerbit. ISBN xxx.",
            "     Jurnal: Penulis, A. A. (Tahun). Judul artikel. *Nama Jurnal, Vol*(No), hlm–hlm. https://doi.org/...",
            "     Standar/Web: Organisasi. (Tahun). *Judul*. URL",
            "6. Gunakan skill `humanizer` (load via tool skill) untuk menulis ulang jawaban agar terdengar "
            "seperti ditulis manusia: hilangkan pola AI (bahasa kaku, kata seperti 'delve', 'landscape', "
        "kalimat berimbuhan berlebihan, dashes, not-X-but-Y, dan sejenisnya). Mode embedded: hasil langsung teks final.",
            "   - Pertahankan semua fakta, rumus, istilah teknis, dan sitasi.",
            "   - Untuk jawaban matematika: berikan langkah penyelesaian sebagai teks + notasi matematika teks yang jelas.",
            f"7. Tulis jawaban final dalam format Markdown ke `{jawaban_path}`. Struktur wajib:",
            "```",
            "## Jawab",
            "(jawaban untuk setiap butir soal, gunakan subheading/penomoran sesuai soal: a, b, c, ...)",
            "",
            "## Daftar Pustaka",
            "1. ...",
            "2. ...",
            "```",
        ]
    )
    if work_kind == "diskusi":
        lines.extend(
            [
                "",
                "8. Argumentasi manfaat (HANYA jika relevan): sebelum menulis, nilai dulu apakah topik soal "
                "punya aplikasi nyata yang jelas (sistem informasi seperti HRIS, organisasi, perusahaan, industri, "
                "atau praktik profesional lain).",
                "   - JIKA relevan: akhiri bagian `## Jawab` dengan sub-bagian `### Manfaat dan Relevansi` berisi "
                "argumentasi mengapa konsep/keterampilan ini berguna di konteks nyata tersebut (mekanisme/alasan "
                "logis, bukan klaim kosong), didukung literatur nyata yang diverifikasi via websearch/webfetch.",
                "   - JIKA TIDAK relevan (soal murni teoretis/abstrak/ hitungan tanpa konteks aplikatif): JANGAN "
                "memaksakan bagian ini, langsung ke `## Daftar Pustaka`. Jangan menulis 'Manfaat dan Relevansi' "
                "yang dibuat-buat.",
                "   - DILARANG menulis tanggapan ke teman/postingan orang lain (tidak ada data teman; fiktif "
                "dilarang).",
            ]
        )
    lines.extend(
        [
            "9. Kembalikan di output terminal hanya satu kalimat status singkat (misal: 'Selesai').",
            "",
            "Penting: ACCURACY > kecepatan. Kerjakan langkah 1-5 sesuai urutan, dan pastikan "
            "jawaban menjawab SEMUA butir dengan Daftar Pustaka yang benar-benar terverifikasi.",
        ]
    )
    return "\n".join(lines)
