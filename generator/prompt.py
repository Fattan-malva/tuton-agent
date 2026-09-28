"""Builder prompt untuk agent `tuton`.

Prinsip: AI yang mengambil soalnya sendiri dari URL, bukan_python yang
menempelkan teks hasil scrape ke prompt. Alasannya praktis, bukan sekadar
selera: scrape kita pasti kehilangan bagian yang paling menentukan nilai --
instruksi khusus tutor, pedoman penilaian (rubrik), contoh soal, dan konteks
diskusi. Kalau AI membaca halaman aslinya, semua itu ikut terbaca dan
jawabannya otomatis lebih dekat dengan ekspektasi dosen.

URL yang dipakai adalah URL Reader Lokal (http://127.0.0.1:.../soal?u=...). Agent
tidak punya cookie Moodle, jadi Reader yang menyuntikkannya. URL Moodle
aslinya tetap disertakan supaya jejaknya jelas dan bisa di-debug.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import Config

_STYLE_RULES = [
    "Gaya jawaban yang diharapkan (menguji cara berpikir, bukan sekadar meniru kalimat dosen): "
    "langsung ke inti, kalimat jelas dan informal-academic. Untuk soal hitungan tulis "
    "langkah penyelesaian berurutan (Diketahui/ditanya -> penyelesaian -> kesimpulan), "
    "pakai sub-bagian a/b/c sesuai butir soal, bahasa formal tapi natural.",
    "Semua perhitungan/rumus yang memuat simbol dan angka ditulis di baris tersendiri "
    "dibungkus $$ ... $$ (hanya satu persamaan per baris), misal:",
    "  $$ 2A = [[4, 2], [0, 6]] $$",
    "  $$ AB = [[0, 13], [-6, 15]] $$",
    "  Notasi yang didukung untuk dikonversi jadi equation Word: matriks [[a, b], [c, d]], "
    "pangkat x^2, akar sqrt(...), operator + - x = .",
]

_HONESTY_RULES = [
    "JANGAN mengarang sumber, tautan, nomor halaman, ISBN, DOI, atau nama penulis. "
    "Referensi yang tidak dapat diverifikasi HARUS dibuang, bukan ditebak.",
    "JANGAN mengklaim sudah membaca dokumen yang tidak kamu akses. Kalau halaman benar-benar "
    "tidak bisa dibuka, nyatakan bagian mana yang tidak diketahui di bagian Catatan/Asumsi.",
    "Jangan menulis placeholder, TODO, 'dst.', atau contoh angka yang tidak berasal dari soal.",
    "Jika satu butir mustahil dijawab dari sumber yang ada, tulis jawaban partial yang "
    "jujur beserta alasannya -- jangan mengarang angka.",
]

_RESEARCH_RULES = [
    "LANGKAH 2 - RISET SUMBER. Sebelum menjawab, kumpulkan sumber nyata yang kredibel "
    "untuk topik ini. Gunakan tool websearch untuk mencari, lalu webfetch untuk MEMERIKSA "
    "setiap kandidat satu per satu. Utamakan urutan berikut:",
    "  1. Buku teks: cari edisi yang benar via Google Books atau Open Library, "
    "verifikasi judul + penulis + tahun + penerbit + ISBN.",
    "  2. Artikel jurnal peer-reviewed: verifikasi lewat Crossref "
    "(webfetch `https://api.crossref.org/works/<DOI>`) atau OpenAlex "
    "(webfetch `https://api.openalex.org/works?search=...`). Hanya DOI yang benar-benar "
    "mengembalikan metadata yang boleh dipakai.",
    "  3. Standar/norma resmi yang gratis: ISO, IEEE, IETF, W3C, WHO, NIST, "
    "dokumentasi resmi (python.org, docs.python.org, nodejs.org, postgresql.org, "
    "developer.mozilla.org).",
    "  4. Jurnal open access: DOAJ, PubMed/PMC, arXiv (periksa lewat "
    "webfetch `https://arxiv.org/abs/<id>`), dan repository institusi.",
    "  5. Sumber sekunder (blog, Stack Overflow, YouTube) HANYA sebagai konteks tambahan, "
    "dan kalau dipakai harus tetap diberi label sumber tidak resmi.",
    "Untuk SETIAP referensi yang dipakai, kamu WAJIB sudah menjalankan webfetch dan melihat "
    "responsnya. Referensi yang webfetch-nya gagal/404 TIDAK boleh masuk Daftar Pustaka.",
]

_AUDIT_RULES = [
    "  [ ] Semua butir soal punya bagian jawaban dengan label yang sama.",
    "  [ ] Tidak ada butir yang dijawab 'seperti di atas' atau 'dapat ditafsirkan begitu saja'.",
    "  [ ] Semua angka hasil hitung sudah dicek ulang; tidak ada yang bertentangan antar bagian.",
    "  [ ] Tidak ada kalimat yang setengah jadi atau terpotong.",
    "  [ ] Semua referensi di Daftar Pustaka sudah pernah diverifikasi via webfetch, "
    "dan tautan/DOI-nya benar-benar hidup.",
    "  [ ] Tidak ada karakter aneh (mis. huruf CJK/Cyrillic) yang nyasar di dalam kata "
    "Indonesia. Tulis ulang dari nol bila perlu - JANGAN melakukan edit kecil-kecil pada "
    "teks yang sudah rusak, karena itu menyisakan fragmen aneh.",
]

_OUTPUT_SKELETON = [
    "## Jawab",
    "(jawaban untuk setiap butir soal, gunakan subheading/penomoran sesuai soal: a, b, c, ...)",
    "",
    "## Daftar Pustaka",
    "1. ...",
    "2. ...",
]


def _identitas() -> str:
    return json.dumps(
        {"Nama": Config.NAMA, "NIM": Config.NIM, "Prodi": Config.PRODI},
        ensure_ascii=False,
    )


def _context(work_kind: str, index: int, course_name: str, section_num: int,
             activity_title: str) -> list[str]:
    return [
        "## Konteks",
        f"- Jenis pekerjaan: {work_kind} ke-{index}",
        f"- Mata kuliah: {course_name}",
        f"- Sesi: {section_num}",
        f"- Judul aktivitas: {activity_title}",
        f"- Identitas mahasiswa: {_identitas()}",
    ]


_HUMANIZER_LINE = (
    "6. Gunakan skill `humanizer` (load via tool skill) untuk menulis ulang jawaban agar "
    "terdengar seperti ditulis manusia: hilangkan pola AI (bahasa kaku, kata seperti "
    "'delve', 'landscape', kalimat berimbuhan berlebihan, dashes, not-X-but-Y, dan "
    "sejenisnya). Mode embedded: hasil langsung teks final. "
    "Pertahankan semua fakta, rumus, istilah teknis, dan sitasi. "
    "Untuk jawaban matematika: berikan langkah penyelesaian sebagai teks + notasi "
    "matematika teks yang jelas."
)

_MANFAAT_RULES = [
    "",
    "9. Argumentasi manfaat (HANYA jika relevan): sebelum menulis, nilai dulu apakah topik "
    "soal punya aplikasi nyata yang jelas (sistem informasi seperti HRIS, organisasi, "
    "perusahaan, industri, atau praktik profesional lain).",
    "   - JIKA relevan: akhiri bagian `## Jawab` dengan sub-bagian `### Manfaat dan Relevansi` "
    "berisi argumentasi mengapa konsep ini berguna di konteks nyata tersebut "
    "(mekanisme/alasan logis, bukan klaim kosong), didukung literatur nyata yang "
    "diverifikasi via websearch/webfetch.",
    "   - JIKA TIDAK relevan (soal murni teoretis/abstrak/hitungan tanpa konteks aplikatif): "
    "JANGAN memaksakan bagian ini, langsung ke `## Daftar Pustaka`.",
    "   - DILARANG menulis tanggapan ke teman/postingan orang lain (tidak ada data "
    "postingan teman; fiktif dilarang).",
]


def build_url_prompt(
    *,
    work_kind: str,
    index: int,
    course_name: str,
    section_num: int,
    activity_title: str,
    soal_urls: list[str],
    source_urls: list[str],
    attachments: list[str],
    transcript_path: Path | None = None,
    lampiran_dir: Path | None = None,
    jawaban_path: Path,
    agent_can_read_files: bool = False,
) -> str:
    """Prompt mode URL: AI ambil sendiri soalnya dari Reader Lokal."""
    lines = [
        f"Kamu adalah asisten pengerjaan {work_kind} tutorial online (tuton).",
        "",
        "SOAL BUKAN diberikan sebagai teks di pesan ini. Kamu harus mengambilnya sendiri "
        "dari URL di bawah memakai tool `webfetch`. URL tersebut sudah diautentikasi dengan "
        "sesi Moodle aktif, jadi isinya adalah halaman resmi dari dosen.",
        "",
        *_context(work_kind, index, course_name, section_num, activity_title),
        "",
        "## URL SUMBER SOAL (ambil dengan webfetch, urut dari atas)",
    ]
    for pos, url in enumerate(soal_urls, 1):
        lines.append(f"{pos}. {url}")
    if source_urls:
        lines.append("")
        lines.append("URL asli di Moodle (untuk-catatan/referensi, tidak bisa dibuka "
                     "langsung karena butuh cookie):")
        lines.extend(f"- {url}" for url in source_urls)

    lines.extend(
        [
            "",
            "## Cara mengambil soal (WAJIB)",
            "1. Panggil webfetch pada URL nomor 1. Baca SELURUH isi hasilnya sampai bawah, "
            "termasuk bagian 'Pedoman Penilaian / Rubrik' dan 'Lampiran' bila ada.",
            "2. Halaman itu adalah konteks resmi. Pahami dengan saksama APAKAH ini Diskusi "
            "atau Tugas, dan apa yang sebenarnya diminta tutor: bukan cuma kalimat "
            "pertanyaannya, tapi juga instruksi khusus, rubrik/pedoman penilaian, "
            "batas kata, jumlah butir, dan semua syarat yang disebut.",
            "3. Kalau URL pertama tidak memuat soal yang lengkap, coba URL berikutnya sampai "
            "satu memuat soal. Gabungkan informasi dari semua sumber yang relevan.",
            "4. JIKA ada lampiran (gambar/PDF/dokumen) yang isinya penting dan belum "
            "tereksir di halaman, ambil isinya dari file lokal di folder lampiran "
            "(lihat bagian Lampiran di bawah) memakai tool `read`.",
        ]
    )
    if attachments or transcript_path:
        lines.extend(["", "## Lampiran"])
        if lampiran_dir:
            lines.append(f"- Folder: `{lampiran_dir}`")
        if attachments:
            lines.append(f"- Berkas: {', '.join(attachments)}")
        if transcript_path:
            lines.extend(
                [
                    f"- Isi lampiran sudah diekstrak otomatis ke `{transcript_path}` "
                    "(hasil OCR/vision atas gambar, PDF, dan dokumen).",
                    "- **Baca file transkrip itu dengan tool `read` bila halaman "
                    "soal belum memuat butir pertanyaan secara lengkap.** Di UT, "
                    "PDF/gambar lampiran sering kali justru zawar utama soal, "
                    "sedangkan halaman hanya berisi instruksi umum.",
                    "- Perlakukan isi transkrip sebagai bagian resmi soal, bukan "
                    "sekadar catatan. setiap butir yang ada di sana wajib dijawab.",
                ]
            )
        if agent_can_read_files:
            lines.append(
                "- Kamu bisa melihat gambar/PDF: kalau transkrip terasa kurang atau "
                "ada bagian `[tidak terbaca]`, buka langsung berkasnya dengan tool `read`."
            )
        else:
            lines.append(
                "- Kamu tidak bisa melihat gambar, jadi andalkan file transkrip di atas. "
                "Kalau ada bagian yang tidak terbaca, sebutkan itu di Catatan dan "
                "jangan mengarang isinya."
            )
        lines.append("- DILARANG menjalankan perintah shell/bash, OCR, crop, atau resize.")

    lines.extend(["", "## Gaya jawaban", *_STYLE_RULES])
    lines.extend(["", "## Aturan kejujuran (WAJIB)", *_HONESTY_RULES])
    lines.extend(
        [
            "",
            "## Cara kerja (WAJIB, ikuti berurutan)",
            "LANGKAH 1 - PETA SOAL. Setelah membaca sumber, buat daftar internal semua "
            "pertanyaan/butir yang harus dijawab (nomor butir: 1, 2, a, b, c, i-iv), "
            "termasuk setiap persyaratan di rubrik atau instruksi khusus. Jangan tulis "
            "peta ini ke file jawaban; ini catatan internal kamu.",
            "",
            *_RESEARCH_RULES,
            "",
            "LANGKAH 3 - JAWAB. Jawab SETIAP butir dari langkah 1, tidak ada yang "
            "dilewati. Untuk setiap butir: (a) kerjakan langkahnya, (b) cek ulang "
            "hasil hitungannya secara independen (hitung ulang dengan cara lain, cek "
            "satuan, cek masuk akal terhadap besaran soal), (c) tulis jawaban akhirnya "
            "di bawah sub-bagian dengan label butir yang sama dengan soal.",
            "",
            "LANGKAH 4 - AUDIT SEBELUM MENULIS. Periksa daftar berikut satu per satu, dan "
            "perbaiki sebelum menulis file:",
            *_AUDIT_RULES,
            "  [ ] Semua syarat/rubrik dari halaman soal sudah dipenuhi dalam jawaban.",
            "",
            "LANGKAH 5 - TULIS. Tulis jawaban final ke file dengan struktur di bawah. Tulis "
            "file sekali secara utuh. Jangan mengedit file berulang kali untuk "
            "'memperbaiki' satu kata - itu pernah merusak jawaban (menyisakan fragmen acak).",
            "",
            "## Instruksi",
            "1. Kerjakan dengan benar dan LENGKAP. Mulai dari URL nomor 1 dan ikuti "
            "urutan langkah 1-5 di atas tanpa kecuali.",
            "2. JANGAN menulis ulang isi soal atau mempotong kutipan dari halaman; cukup "
            "jawabannya. Kutipan singkat sebagai bukti boleh, dengan tanda kutip.",
            "3. Jika setelah mencoba semua URL sumber, soal benar-benar tidak tersedia: "
            "JANGAN mengarang. Tulis di file jawaban `## Jawab` lalu paragraf yang "
            "menjelaskan sumber mana yang gagal diakses dan apa yang tidak diketahui, "
            "lalu akhiri dengan Daftar Pustaka kosong bila tidak ada sumber yang dipakai. "
            "Jangan menulis jawaban fiktif.",
            "   Jika sebagian ada yang '[tidak terbaca]', kerjakan bagian yang terbaca dan "
            "sebutkan asumsi yang kamu pakai di bagian Catatan.",
            "4. Sertakan 'Daftar Pustaka' di akhir jawaban yang BERISI HANYA referensi NYATA "
            "dan sudah diverifikasi lewat webfetch:",
            "   - Setiap entri harus bisa dibuka pembaca lain: sertakan tautan stabil (DOI "
            "resolver https://doi.org/..., URL penerbit/arxiv/repositori, atau ISBN).",
            "   - Kalau sebuah buku tidak punya URL gratis, tetap tulis ISBN-nya.",
            "   - Pilih 3-8 entri yang paling relevan dengan butir soal.",
            "   - Format APA edisi ke-7:",
            "     Buku  : Penulis, A. A., & Penulis, B. B. (Tahun). *Judul Buku* (edisi). "
            "Penerbit. ISBN xxx.",
            "     Jurnal: Penulis, A. A. (Tahun). Judul artikel. *Nama Jurnal, Vol*(No), "
            "hlm-hlm. https://doi.org/...",
            "     Standar/Web: Organisasi. (Tahun). *Judul*. URL",
            _HUMANIZER_LINE,
            f"7. Tulis jawaban final dalam format Markdown ke `{jawaban_path}`. Struktur wajib:",
            "```",
            *_OUTPUT_SKELETON,
            "```",
        ]
    )
    if work_kind == "diskusi":
        lines.extend(_MANFAAT_RULES)
    lines.extend(
        [
            "",
            "Penting: AKURASI > kecepatan. Kerjakan langkah 1-5 sesuai urutan, dan pastikan "
            "jawaban menjawab SEMUA butir dengan Daftar Pustaka yang benar-benar terverifikasi.",
        ]
    )
    return "\n".join(lines)


def build_file_prompt(
    *,
    work_kind: str,
    index: int,
    course_name: str,
    section_num: int,
    activity_title: str,
    soal_path: Path,
    attachment_dir: Path,
    lampiran: list[str],
    jawaban_path: Path,
) -> str:
    """Prompt mode file (perilaku lama): teks soal ditempel ke file soal.md.

    Dipertahankan sebagai jalur cadangan/A-B test lewat `--soal-mode file`.
    """
    lines = [
        f"Kamu adalah asisten pengerjaan {work_kind} tutorial online (tuton).",
        "Selesaikan pertanyaan yang ada di file soal, lalu TULIS jawaban final ke path "
        "yang ditentukan.",
        "",
        *_context(work_kind, index, course_name, section_num, activity_title),
        "",
        "## Bahan",
        f"- Soal: baca file `{soal_path}`. Seluruh isi lampiran sudah diekstrak ke file "
        "tersebut pada bagian 'Isi lampiran ... (transkripsi)'.",
        f"- DILARANG membuka/membaca file di folder lampiran `{attachment_dir}`.",
    ]
    if lampiran:
        lines.append(f"  Isi folder: {', '.join(lampiran)}")
    lines.extend(["", "## Gaya jawaban", *_STYLE_RULES])
    lines.extend(["", "## Aturan kejujuran (WAJIB)", *_HONESTY_RULES])
    lines.extend(
        [
            "",
            "## Cara kerja (WAJIB, ikuti berurutan)",
            "LANGKAH 1 - PETA SOAL. Baca file soal dari atas sampai bawah, lalu buat daftar "
            "internal semua pertanyaan/butir yang harus dijawab. Jangan tulis peta ini ke "
            "file jawaban.",
            "",
            *_RESEARCH_RULES,
            "",
            "LANGKAH 3 - JAWAB. Jawab SETIAP butir dari peta langkah 1, tidak ada yang "
            "dilewati. Untuk setiap butir: (a) kerjakan langkahnya, (b) cek ulang hasil "
            "hitungannya secara independen, (c) tulis jawaban akhirnya di bawah "
            "sub-bagian dengan label butir yang sama dengan soal.",
            "",
            "LANGKAH 4 - AUDIT SEBELUM MENULIS. Periksa daftar berikut satu per satu:",
            *_AUDIT_RULES,
            "",
            "LANGKAH 5 - TULIS. Tulis jawaban final sekaligus secara utuh; jangan "
            "mengedit berulang.",
            "",
            "## Instruksi",
            f"1. Pahami soal yang tertulis di file `{soal_path}`. Kerjakan dengan benar "
            "dan LENGKAP.",
            "2. JANGAN menjalankan perintah shell/bash. JANGAN meng-OCR file lampiran. "
            "Semua isi lampiran sudah tersedia sebagai teks di dalam file soal.",
            "3. Jika teks soal benar-benar TIDAK ADA, JANGAN mengarang. Tulis di file "
            "jawaban: '## Jawab' lalu penjelasan bahwa soal tidak ditemukan, lalu akhiri.",
            "4. Jangan menulis ulang isi soal di jawaban. Cukup jawabannya.",
            "5. Sertakan 'Daftar Pustaka' di akhir jawaban yang BERISI HANYA referensi NYATA "
            "dan sudah diverifikasi lewat webfetch.",
            _HUMANIZER_LINE,
            f"7. Tulis jawaban final dalam format Markdown ke `{jawaban_path}`. Struktur wajib:",
            "```",
            *_OUTPUT_SKELETON,
            "```",
        ]
    )
    if work_kind == "diskusi":
        lines.extend(_MANFAAT_RULES)
    lines.extend(
        [
            "",
            "Penting: ACCURACY > kecepatan. Kerjakan langkah 1-5 sesuai urutan, dan "
            "pastikan jawaban menjawab SEMUA butir dengan Daftar Pustaka yang benar-benar "
            "terverifikasi.",
        ]
    )
    return "\n".join(lines)


def build_prompt(**kwargs) -> str:
    """Pintu masuk tunggal. Mode ditentukan oleh `soal_urls` yang diberikan."""
    mode = kwargs.pop("mode", "url")
    if mode == "file" or not kwargs.get("soal_urls"):
        return build_file_prompt(**kwargs)
    return build_url_prompt(**kwargs)
