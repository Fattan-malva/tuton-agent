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
            "## Instruksi",
            f"1. Pahami soal yang tertulis di file `{soal_path}`. Kerjakan dengan benar dan LENGKAP, tidak melewatkan butir soal.",
            "2. JANGAN menjalankan perintah shell/bash apa pun. JANGAN membaca, memproses, atau meng-OCR file "
            "lampiran (gambar/PDF/Excel). JANGAN crop, resize, atau render ASCII. Semua isi lampiran sudah "
            "tersedia sebagai teks di dalam file soal.",
            "3. Jika teks soal kurang jelas / berisi '[tidak terbaca]', kerjakan dengan asumsi yang wajar dan "
            "cantumkan asumsinya di akhir jawaban.",
            "4. Jangan menulis ulang isi soal di jawaban. Cukup jawabannya.",
            "5. Sertakan 'Daftar Pustaka' di akhir jawaban yang BERISI HANYA referensi NYATA dan dapat diverifikasi:",
            "   - Pakai tool websearch/webfetch untuk memverifikasi setiap referensi benar-benar ada "
            "   (buku, jurnal, artikel; cek di Google Scholar / penerbit / DOI Crossref).",
            "   - JANGAN membuat referensi palsu atau halusinasi. Referensi yang tidak bisa dipastikan aslinya dibuang.",
            "   - Format APA edisi ke-7:",
            "     Buku  : Penulis, A. A., & Penulis, B. B. (Tahun). *Judul Buku* (edisi). Penerbit.",
            "     Jurnal: Penulis, A. A. (Tahun). Judul artikel. *Nama Jurnal, Vol*(No), hlm–hlm. https://doi.org/...",
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
            "8. Kembalikan di output terminal hanya satu kalimat status singkat (misal: 'Selesai').",
            "",
            "Penting: ACCURACY > kecepatan. Periksa kembali jawaban sebelum menulis file.",
        ]
    )
    return "\n".join(lines)