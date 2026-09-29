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
    "pakai sub-bagian a/b/c sesuai soal, bahasa formal tapi natural.",
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
    "Jika satu soal mustahil dijawab dari sumber yang ada, tulis jawaban partial yang "
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
    "  [ ] Semua soal punya bagian jawaban dengan label yang sama.",
    "  [ ] Tidak ada soal yang dijawab 'seperti di atas' atau 'dapat ditafsirkan begitu saja'.",
    "  [ ] Semua angka hasil hitung sudah dicek ulang; tidak ada yang bertentangan antar bagian.",
    "  [ ] Tidak ada kalimat yang setengah jadi atau terpotong.",
    "  [ ] Daftar Pustaka di file jawaban identik dengan isi file referensi yang "
    "diberikan - tidak ditambah, tidak dikurangi, tidak diubah.",
    "  [ ] Semua syarat format yang diminta tutor (batas kata, jumlah soal, bentuk "
    "tabel, jumlah desimal, spasi, dan sejenisnya) benar-benar dipenuhi.",
    "  [ ] Tidak ada karakter aneh (mis. huruf CJK/Cyrillic) yang nyasar di dalam kata "
    "Indonesia. Tulis ulang dari nol bila perlu - JANGAN melakukan edit kecil-kecil pada "
    "teks yang sudah rusak, karena itu menyisakan fragmen aneh.",
]

# Aturan untuk agen PENULIS. Riset sudah dipindah ke agen `pencari-pustaka`
# yang terpisah, jadi di sini riset justru dilarang: kalau dua pihak sama-sama
# mencari referensi, biaya terbuang dua kali untuk hasil yang sama.
_NO_RESEARCH_RULES = [
    "DILARANG mencari referensi sendiri. Jangan pakai websearch. Jangan pakai "
    "webfetch untuk mencari atau memverifikasi sumber. Referensi sudah disiapkan "
    "di file yang disebutkan di bawah.",
    "Bagian '## Daftar Pustaka' di file jawaban HARUS berupa salinan persis dari "
    "file referensi tersebut: entris yang sama, urutan yang sama, penulisan yang "
    "sama. Jangan menambah entri, jangan mengoreksi, jangan menulis referensi dari "
    "ingat model sendiri.",
    "Kalau file referensi berisi satu baris 'TIDAK ADA REFERENSI YANG TERVERIFIKASI', "
    "tulis tepat baris itu di bagian Daftar Pustaka. Jangan mengarang pengganti.",
    "Dalam teks jawaban, boleh merujuk '(Rosen, 2011)' untuk sumber yang memang "
    "ada di daftar. Jangan mengarang sitasi untuk sumber yang tidak ada di sana.",
]

_OUTPUT_SKELETON = [
    "## Jawab",
    "(jawaban untuk setiap soal, gunakan subheading/penomoran sesuai soal: a, b, c, ...)",
    "",
    "## Daftar Pustaka",
    "1. ...",
    "2. ...",
]

# Kerangka jawaban untuk agen penulis. Level heading di sini bukan gaya penulisan:
# `##` dan `###` dipetakan langsung ke style "Heading 2" dan "Heading 3" dari
# template .docx, jadi tingkatnya menentukan tampilan dokumen, bukan hanya
# struktur markdown. Mengubah `## Jawaban Mahasiswa` menjadi `## Jawab`
# memindahkan dokumen ke sub-bagian yang salah.
_WRITER_SKELETON = [
    "## <Judul Soal>",
    "",
    "## Jawaban Mahasiswa",
    "### <Sub-bagian pertama>",
    "<isi jawaban soal pertama, dengan penomoran yang sama seperti di soal>",
    "### <Sub-bagian berikutnya>",
    "...",
    "### Kesimpulan",
    "<kesimpulan akhir>",
    "",
    "## Daftar Pustaka",
    "1. <salinan persis entri pertama dari berkas referensi>",
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

# Versi aturan manfaat untuk agen PENULIS. Bedanya cuma satu dari
# `_MANFAAT_RULES`: di sini tidak boleh menyebut websearch/webfetch, karena
# agen penulis sudah dilarang riset dan referensinya datang dari berkas terpisah.
# `_MANFAAT_RULES` yang asli sengaja dibiarkan utuh karena masih dipakai
# `build_file_prompt` (jalur Form Soal) yang memang masih melakukan riset.
_MANFAAT_RULES_WRITER = [
    "",
    "9. Argumentasi manfaat (HANYA jika relevan): sebelum menulis, nilai dulu apakah topik "
    "soal punya aplikasi nyata yang jelas (sistem informasi seperti HRIS, organisasi, "
    "perusahaan, industri, atau praktik profesional lain).",
    "   - JIKA relevan: akhiri bagian jawaban dengan sub-bagian "
    "`### Manfaat dan Relevansi` berisi argumentasi mengapa konsep ini berguna di "
    "konteks nyata tersebut (mekanisme atau alasan logis, bukan klaim kosong), dan "
    "merujuk hanya sumber yang sudah ada di Daftar Pustaka.",
    "   - JIKA TIDAK relevan (soal murni teoretis, abstrak, atau hitungan tanpa konteks "
    "aplikatif): JANGAN memaksakan bagian ini, langsung ke `## Daftar Pustaka`.",
    "   - DILARANG menulis tanggapan ke teman atau postingan orang lain (tidak ada "
    "data postingan teman; fiktif dilarang).",
]


def build_writer_prompt(
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
    petak_path: Path | None = None,
    pustaka_path: Path | None = None,
) -> str:
    """Prompt agen penulis: baca peta soal + daftar pustaka, lalu susun jawaban.

    Dua file lokal menggantikan pencarian yang sebelumnya agen ini lakukan sendiri:

    - `petak_path`   peta soal hasil agen `pemetak-soal` (satu kali per sesi,
                     di-cache). Berisi soal, syarat format, rubrik, dan
                     lampiran yang relevan.
    - `pustaka_path` daftar referensi hasil agen `pencari-pustaka` (satu kali
                     per item, di-cache).

    Efeknya: satu sesi berisi lima item tidak lagi dibaca lima kali oleh model
    kuat. Sekali saja oleh model kecil, lalu hasilnya dipakai bersama.

    Kalau `petak_path` tidak ada (tahap pemetaan gagal), prompt otomatis
    memakai jalur lama: ambil soalnya sendiri dari `soal_urls` dengan webfetch.
    Jadi kegagalan tahap 0 menurunkan kualitas, bukan menghentikan pipeline.
    """
    pakai_peta = bool(petak_path and Path(petak_path).is_file())
    lines = [
        f"Kamu adalah asisten pengerjaan {work_kind} tutorial online (tuton).",
        "",
        *_context(work_kind, index, course_name, section_num, activity_title),
    ]

    if pakai_peta:
        lines.extend(
            [
                "",
                "## Peta soal (WAJIB dibaca paling dulu)",
                f"Baca file `{petak_path}` dengan tool `read` SEBELUM melakukan apa pun. "
                "File itu hasil agen pemetaan yang sudah menelusuri halaman Moodle untuk "
                "sesi ini, jadi isinya sudah gathered: soal, syarat format, rubrik, "
                "dan daftar lampiran yang relevan.",
                "",
                "Isi peta adalah rujukan utama kerjamu. Aturan memakainya:",
                "  1. Kerjakan SETIAP soal yang tertulis di peta. Soal yang tidak "
                "dijawab berarti nilai hilang.",
                "  2. Patuhi syarat format di peta SECARA HARFIAH (batas kata, jumlah "
                "soal, bentuk tabel, jumlah desimal, dan sejenisnya). Pelanggaran "
                "format adalah alasan paling sering jawaban dinyatakan salah bentuk.",
                "  3. Kalau peta menyebut rubrik atau pedoman penilaian, pastikan setiap "
                "aspek rubrik itu kelihatan di jawabanmu.",
                "  4. Kalau peta menandai ada soal yang bergantung lampiran atau materi "
                "lain, WAJIB buka lampiran itu (lihat bagian Lampiran di bawah) sebelum "
                "menjawab soal tersebut. Jangan menjawab dari asumsi.",
                "  5. Cadangan saja: kalau peta ternyata tidak memuat soalnya secara "
                "lengkap (soal hilang, atau ada judul tanpa pertanyaannya), boleh buka "
                "halaman aslinya dengan webfetch pada URL di bawah. Ini pengecualian, "
                "bukan langkah wajib. Jangan lakukan bila peta sudah cukup.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Cara mengambil soal (WAJIB)",
                "Peta soal tidak tersedia untuk sesi ini, jadi kamu harus mengambil "
                "soalnya sendiri. Panggil webfetch pada URL di bawah, urut dari nomor "
                "1, dan baca SELURUH isi hasilnya sampai bawah termasuk bagian "
                "'Pedoman Penilaian / Rubrik' dan 'Lampiran' bila ada.",
            ]
        )

    lines.extend(["", "## URL sumber (dibaca dengan webfetch, hanya bila perlu)"])
    for pos, url in enumerate(soal_urls, 1):
        lines.append(f"{pos}. {url}")
    if source_urls:
        lines.append("")
        lines.append(
            "URL asli di Moodle (untuk catatan/referensi, tidak bisa dibuka langsung "
            "karena butuh cookie):"
        )
        lines.extend(f"- {url}" for url in source_urls)

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
                    "- Baca file transkrip itu dengan tool `read` bila soalnya "
                    "pertanyaan ada di dalam lampiran dan tidak tertulis di halaman "
                    "soal. Di UT, PDF atau gambar lampiran sering justru zawarnya, "
                    "sedangkan halaman hanya berisi instruksi umum.",
                    "- Perlakukan isi transkrip sebagai bagian resmi soal, bukan "
                    "sekadar catatan. Setiap soal yang ada di sana wajib dijawab.",
                ]
            )
        if agent_can_read_files:
            lines.append(
                "- Kamu bisa melihat gambar/PDF: kalau transkrip terasa kurang atau ada "
                "bagian `[tidak terbaca]`, buka langsung berkasnya dengan tool `read`."
            )
        else:
            lines.append(
                "- Kamu tidak bisa melihat gambar, jadi andalkan file transkrip di atas. "
                "Kalau ada bagian yang tidak terbaca, sebutkan itu di Catatan dan "
                "jangan mengarang isinya."
            )
        lines.append(
            "- DILARANG menjalankan perintah shell/bash, OCR, crop, atau resize."
        )

    if pustaka_path and Path(pustaka_path).is_file():
        lines.extend(
            [
                "",
                "## Referensi (WAJIB dipakai, jangan dicari ulang)",
                f"Baca file `{pustaka_path}` dengan tool `read`. Isinya adalah Daftar "
                "Pustaka final untuk soal ini, sudah diverifikasi oleh agen terpisah. "
                "Salin persis ke bagian `## Daftar Pustaka` pada file jawabanmu.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Referensi",
                "Berkas referensi tidak tersedia. Tulis `## Daftar Pustaka` lalu satu "
                "baris `TIDAK ADA REFERENSI YANG TERVERIFIKASI`. Jangan mengarang "
                "referensi dari ingatan model.",
            ]
        )

    lines.extend(["", "## Gaya jawaban", *_STYLE_RULES])
    lines.extend(["", "## Aturan kejujuran (WAJIB)", *_HONESTY_RULES])
    lines.extend(["", "## Aturan referensi (WAJIB)", *_NO_RESEARCH_RULES])
    lines.extend(
        [
            "",
            "## Cara kerja (WAJIB, ikuti berurutan)",
            "LANGKAH 1 - PETA INTERNAL. Dari peta soal dan lampiran, buat daftar internal "
            "semua soal yang harus dijawab, termasuk setiap persyaratan format. Jangan "
            "tulis daftar ini ke file jawaban; ini catatan internal kamu.",
            "",
            "LANGKAH 2 - JAWAB. Jawab SETIAP soal dari langkah 1, tidak ada yang "
            "dilewati. Untuk setiap soal: (a) kerjakan langkahnya, (b) cek ulang hasil "
            "hitungannya secara independen (hitung ulang dengan cara lain, cek satuan, "
            "cek masuk akal terhadap besaran soal), (c) tulis jawaban akhirnya di bawah "
            "sub-bagian dengan label soal yang sama dengan soal.",
            "",
            "LANGKAH 3 - AUDIT SEBELUM MENULIS. Periksa daftar berikut satu per satu, "
            "dan perbaiki sebelum menulis file:",
            *_AUDIT_RULES,
            "",
            "LANGKAH 4 - TULIS. Tulis jawaban final ke file dengan struktur di bawah. "
            "Tulis file sekali secara utuh. Jangan mengedit file berulang kali untuk "
            "'memperbaiki' satu kata; itu pernah merusak jawaban dan menyisakan "
            "fragmen acak.",
            "",
            "## Instruksi",
            "1. Kerjakan dengan benar dan LENGKAP. Ikuti urutan langkah 1-4 di atas "
            "tanpa kecuali.",
            "2. JANGAN menulis ulang isi soal atau mempotong kutipan dari halaman; cukup "
            "jawabannya. Kutipan singkat sebagai bukti boleh, dengan tanda kutip.",
            "3. Jika setelah membaca peta, lampiran, dan URL cadangan, soal benar-benar "
            "tidak tersedia: JANGAN mengarang. Tulis di file jawaban bagian `## Jawab` "
            "lalu paragraf yang menjelaskan sumber mana yang tidak bisa diakses dan apa "
            "yang tidak diketahui. Jangan menulis jawaban fiktif.",
            "4. Kalau sebagian ada yang '[tidak terbaca]', kerjakan bagian yang terbaca "
            "dan sebutkan asumsi yang kamu pakai di bagian Catatan.",
            _HUMANIZER_LINE,
            f"7. Tulis jawaban final dalam format Markdown ke `{jawaban_path}`. "
            "Struktur wajib:",
            "```",
            *_WRITER_SKELETON,
            "```",
        ]
    )
    if work_kind == "diskusi":
        lines.extend(_MANFAAT_RULES_WRITER)
    lines.extend(
        [
            "",
            "Penting: AKURASI lebih penting daripada kecepatan. Kerjakan langkah 1-4 "
            "sesuai urutan, dan pastikan jawaban menjawab SEMUA soal dengan Daftar "
            "Pustaka yang persis sama seperti berkas referensi.",
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
    format_path: Path | None = None,
    format_note: str = "",
) -> str:
    """Prompt mode file (jalur Form Soal).

    `format_path` dan `format_note` berasal dari field "Format Jawaban" yang
    opsional di form. Kalau keduanya kosong, prompt ini persis sama dengan
    versi sebelumnya dan dokumen keluaran memakai template standar.

    Kalau ada isinya, dua hal berubah dan tidak ada yang lain:
      - `format_path`  berkas .docx contoh format milik pengguna. Python
        menyalinnya sebagai dokumen dasar, sehingga hasil .docx mengikuti
        tata letak, font, ukuran halaman, dan style yang benar-benar dipakai
        pengguna -- bukan tebakan.
      - `format_note`  keterangan tambahan dari pengguna. Isi teks jawabannya
        tetap ditulis model memakai style asli berkas contoh itu, bukan style
        bawaan template.
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

    if format_path or format_note.strip():
        lines.extend(["", "## Format jawaban (WAJIB, mengikuti berkas contoh)"])
        if format_path:
            lines.extend(
                [
                    f"Berkas contoh format: `{format_path}`.",
                    "Ini dokumen .docx milik mahasiswa yang berisi contoh jawaban dengan "
                    "tata letak yang benar. **Buka dan periksa strukturnya lebih dulu** "
                    "dengan tool `read` kalau kamu bisa; kalau tidak bisa, andalkan "
                    "keterangan di bawah.",
                    "Ikuti struktur itu persis: jumlah dan urutan sub-bagian, apakah "
                    "pakai tabel atau daftar, anak judul apa yang dipakai, dan di mana "
                    "kesimpulan diletakkan.",
                    "Soal MUAT: struktur dokumen, penataan paragraf, margin, ukuran "
                    "halaman, nama font, ukuran font, warna, spasi, penomoran, dan "
                    "tabel identitas. Pipeline sudah meneruskannya ke berkas keluaran, "
                    "jadi kamu tidak perlu menyalin gaya itu sendiri.",
                    "Yang belum ditangani pipeline adalah ISI: gunakan style yang benar "
                    "saat mengisi setiap sub-bagian, dengan panjang yang sesuai contoh.",
                ]
            )
        if format_note.strip():
            lines.extend(
                [
                    "",
                    "Keterangan tambahan dari mahasiswa:",
                    format_note.strip(),
                ]
            )
        lines.extend(
            [
                "",
                "Kalau keterangan dan berkas contoh saling berbeda, ikuti BERKAS "
                "CONTOH untuk bentuk dan keterangan untuk isi.",
            ]
        )
    lines.extend(
        [
            "",
            "## Cara kerja (WAJIB, ikuti berurutan)",
            "LANGKAH 1 - PETA SOAL. Baca file soal dari atas sampai bawah, lalu buat daftar "
            "internal semua pertanyaan/soal yang harus dijawab. Jangan tulis peta ini ke "
            "file jawaban.",
            "",
            *_RESEARCH_RULES,
            "",
            "LANGKAH 3 - JAWAB. Jawab SETIAP soal dari peta langkah 1, tidak ada yang "
            "dilewati. Untuk setiap soal: (a) kerjakan langkahnya, (b) cek ulang hasil "
            "hitungannya secara independen, (c) tulis jawaban akhirnya di bawah "
            "sub-bagian dengan label soal yang sama dengan soal.",
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
            "pastikan jawaban menjawab SEMUA soal dengan Daftar Pustaka yang benar-benar "
            "terverifikasi.",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt agen pembantu.
#
# Dipisah dari prompt agen penulis karena tugasnya berbeda jenis: yang satu
# menulis jawaban panjang, yang satu hanya menyusun artefak pendek yang dibaca
# agent lain.
#
# `build_petak_prompt` sengaja dibuat sangat tipis. Petunjuk sebenarnya sudah
# ada di definisi agen `.opencode/agent/pemetak-soal.md`, jadi mengulangnya di
# sini hanya menambah token pada setiap pemanggilan. Yang dikirim ke sini
# hanyalah fakta yang tidak diketahui opencode dari definisi agent: nama mata
# kuliah, nomor sesi, URL, dan lokasi berkas keluaran.
# ---------------------------------------------------------------------------


def build_petak_prompt(
    *,
    course_name: str,
    section_num: int,
    section_title: str,
    section_url: str,
    out_path: Path,
) -> str:
    """Prompt untuk agen `pemetak-soal`: satu peta soal untuk satu sesi."""
    lines = [
        f"Petakan soal untuk satu sesi mata kuliah: **{course_name}**, "
        f"sesi ke-{section_num}"
        + (f" ({section_title})" if section_title.strip() else "")
        + ".",
        "",
        f"- Halaman seksi (URL Reader, sudah diautentikasi): {section_url}",
        f"- Tulis peta soal ke: `{out_path}`",
        "",
        "Ikuti aturan di definisi agent kamu. Ringkasnya: telusuri halaman ini "
        "untuk menemukan semua soal yang ada di sesi ini, pahami setiap soal, lalu "
        "tulis peta ke berkas di atas.",
    ]
    return "\n".join(lines)


def build_referensi_prompt(
    *,
    work_kind: str,
    index: int,
    course_name: str,
    section_num: int,
    activity_title: str,
    petak_digest: str,
    transcript_path: Path | None,
    attachment_names: list[str],
    out_path: Path,
    max_refs: int,
) -> str:
    """Prompt untuk agen `pencari-pustaka`: daftar referensi untuk satu item.

    `petak_digest` adalah potongan peta soal milik item ini. Potongan itu
    penting: daftar referensi untuk satu soal tidak boleh ikut soal lain,
    karena hanya referensi yang benar-benar relevan yang membuat daftar ini
    berguna.
    """
    lines = [
        f"Cari daftar pustaka untuk satu soal: {work_kind} ke-{index}, mata kuliah "
        f"{course_name}, sesi {section_num}.",
        "",
        f"- Judul aktivitas: {activity_title}",
        f"- Batas jumlah referensi: **{max_refs}**. Batas keras, bukan saran.",
    ]
    if petak_digest.strip():
        lines.extend(
            [
                "",
                "## Isi soal (hasil pemetaan)",
                "Bagian ini sudah dipetakan oleh agen sebelumnya. Pakai untuk "
                "membaca topik sebenarnya, bukan hanya judulnya.",
                "",
                petak_digest.strip(),
            ]
        )
    if attachment_names:
        lines.extend(["", f"- Lampiran yang menyertai: {', '.join(attachment_names)}"])
    if transcript_path and Path(transcript_path).is_file():
        lines.append(
            f"- Isi lampiran sudah diekstrak ke `{transcript_path}`. **Baca dulu** "
            "kalau kamu punya tool `read`, karena soalnya sering ada di dalam "
            "lampiran dan bukan di halaman."
        )
    lines.extend(
        [
            "",
            f"Tulis Daftar Pustaka ke `{out_path}`. Ikuti aturan di definisi agent "
            "kamu, terutama batas jumlah referensi dan larangan mengarang. Jangan "
            "menjawab soal.",
        ]
    )
    return "\n".join(lines)


def build_prompt(**kwargs) -> str:
    """Pintu masuk tunggal. Mode ditentukan oleh `soal_urls` yang diberikan.

    `mode="file"` adalah jalur Form Soal dan tidak berubah sama sekali: teks soal
    ditempel ke `soal.md`, lalu agen `tuton` mencari referensi sendiri seperti
    sebelumnya. Jalur itu tidak memakai peta soal maupun daftar pustaka terpisah.
    """
    mode = kwargs.pop("mode", "url")
    if mode == "file" or not kwargs.get("soal_urls"):
        return build_file_prompt(**kwargs)
    return build_writer_prompt(**kwargs)
