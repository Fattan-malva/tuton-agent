"""Agent runner in-process: prompt + tool loop lewat endpoint OpenAI-compatible.

Spec agent dibaca dari `agents/<nama>.md`; tidak ada proses eksternal.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from tuton import agent_tools
from tuton import attachments
from tuton import config
from tuton import mcp_client
from tuton import openai_client
from tuton import runtime_config

MAKS_LANGKAH = 40
_SUFFIX_GAMBAR = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class Jalan:
    teks: str = ""
    galat: str = ""
    ditolak: bool = False
    batas_waktu: bool = False
    durasi: float = 0.0
    usage: dict = field(default_factory=dict)
    perintah: list[str] = field(default_factory=list)


def _spesifikasi(nama: str) -> tuple[str, set[str]]:
    """Body prompt dan aksi yang diizinkan dari satu spec agent."""
    path = config.AGENTS_DIR / f"{nama}.md"
    if not path.is_file():
        raise ValueError(f"Spec agent `{nama}` tidak ada di {config.AGENTS_DIR}.")
    isi = path.read_text(encoding="utf-8", errors="replace")
    lines = isi.splitlines()
    if lines and lines[0].strip() == "---":
        akhir = 1
        while akhir < len(lines) and lines[akhir].strip() != "---":
            akhir += 1
        frontmatter = lines[1:akhir]
        body = "\n".join(lines[akhir + 1:])
    else:
        frontmatter, body = [], isi

    izin: set[str] = set()
    for baris in frontmatter:
        m = re.match(r"\s*tools:\s*(.+)$", baris)
        if m:
            izin = {t.strip() for t in m.group(1).split(",") if t.strip()}
    return body.strip(), izin


def _lampiran(berkas: list[Path]) -> tuple[str, list[dict]]:
    """Teks tambahan dan bagian gambar untuk pesan user."""
    teks: list[str] = []
    gambar: list[dict] = []
    for path in berkas or []:
        try:
            if path.suffix.lower() in _SUFFIX_GAMBAR:
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                gambar.append(
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
                )
                continue
            isi, catatan = attachments._baca_isi(path, with_gambar=False)
            blok = f"\n\n## Lampiran: {path.name}\n{isi.strip()[:40000]}"
            if catatan:
                blok += "\n" + "\n".join(f"({c})" for c in catatan)
            teks.append(blok)
        except Exception as exc:  # noqa: BLE001 - lampiran rusak tidak boleh menghentikan agent
            teks.append(f"\n\n## Lampiran: {path.name}\n(tidak bisa dibaca: {exc})")
    return "".join(teks), gambar


def _pesan(nama_agent: str, prompt: str, cwd: Path, berkas: list[Path]) -> tuple[list[dict], set[str]]:
    body, izin = _spesifikasi(nama_agent)
    tambahan, gambar = _lampiran(berkas)
    sistem = (
        f"{body}\n\n"
        "## Lingkungan kerja\n"
        f"Folder kerja: {cwd}\n"
        f"Tanggal hari ini: {date.today().isoformat()}\n"
        "Tulis berkas hasil dengan path relatif terhadap folder kerja. "
        "Kalau pekerjaan selesai, akhiri jawaban dengan baris `SELESAI`."
    )
    isi_user = prompt + tambahan
    if gambar:
        pesan_user = {
            "role": "user",
            "content": [{"type": "text", "text": isi_user}, *gambar],
        }
    else:
        pesan_user = {"role": "user", "content": isi_user}
    return [{"role": "system", "content": sistem}, pesan_user], izin


def _mcp(nama_agent: str) -> tuple[list[dict], dict[str, dict]]:
    definisi: list[dict] = []
    peta: dict[str, dict] = {}
    for server in runtime_config.mcp_untuk(nama_agent):
        tools = mcp_client.tools_untuk(server)
        for t in tools:
            peta[t["function"]["name"]] = server
        definisi.extend(tools)
    return definisi, peta


def _teks_tool(hasil: str, maks: int = 16000) -> str:
    hasil = str(hasil or "")
    if len(hasil) > maks:
        return hasil[:maks] + f"\n[... dipotong, {len(hasil) - maks} karakter lagi ...]"
    return hasil or "(kosong)"


def jalankan(
    *,
    nama: str,
    prompt: str,
    model: str,
    berkas: list[Path] | None = None,
    cwd: Path | None = None,
    batas: float | None = None,
    cancel_event=None,
    lapor=None,
) -> Jalan:
    mulai = time.monotonic()
    hasil = Jalan(perintah=["builtin", nama, model])
    cwd = Path(cwd or config.BASE_DIR)

    def kabar(level: str, msg: str) -> None:
        if lapor is not None:
            lapor(level, msg)

    try:
        penyedia, model_id = runtime_config.resolve(model)
        base_url = str(penyedia.get("base_url") or "")
        api_key = str(penyedia.get("api_key") or "")
        if not base_url:
            raise ValueError(f"Provider `{penyedia.get('id')}` belum punya base URL.")

        messages, izin = _pesan(nama, prompt, cwd, list(berkas or []))
        if "skill" in izin:
            tersedia = sorted(
                p.parent.name
                for p in config.SKILLS_DIR.glob("*/SKILL.md")
            )
            if tersedia:
                messages[0]["content"] += (
                    "\n\nSkill yang bisa dimuat dengan tool `skill`: "
                    + ", ".join(tersedia)
                )
        mcp_tools, peta_mcp = _mcp(nama)
        tools = agent_tools.tools_untuk(izin, mcp_tools)

        for langkah in range(1, MAKS_LANGKAH + 1):
            if cancel_event is not None and cancel_event.is_set():
                raise openai_client.Dibatalkan("Job dihentikan pengguna.")
            if batas is not None and time.monotonic() - mulai >= batas:
                raise openai_client.GalatProvider(
                    f"Melewati batas waktu {int(batas)} detik.", batas_waktu=True
                )
            sisa = None if batas is None else max(1.0, batas - (time.monotonic() - mulai))
            jawab = openai_client.chat(
                base_url=base_url,
                api_key=api_key,
                model=model_id,
                messages=messages,
                tools=tools,
                timeout=min(180, int(sisa or 180)),
                batas=sisa,
                cancel_event=cancel_event,
            )
            for k, v in (jawab.usage or {}).items():
                if isinstance(v, (int, float)):
                    hasil.usage[k] = hasil.usage.get(k, 0) + v

            pesan_assistant: dict = {"role": "assistant", "content": jawab.content or None}
            if jawab.tool_calls:
                pesan_assistant["tool_calls"] = jawab.tool_calls
            messages.append(pesan_assistant)

            if jawab.content.strip():
                baris = jawab.content.strip().splitlines()[0].strip()
                kabar("text", baris[:110])

            if not jawab.tool_calls:
                hasil.teks = jawab.content.strip()
                break

            for call in jawab.tool_calls:
                fungsi = call.get("function") or {}
                nama_tool = str(fungsi.get("name") or "")
                mentah = str(fungsi.get("arguments") or "{}")
                try:
                    args = json.loads(mentah) if mentah.strip() else {}
                except ValueError:
                    args = {}
                kabar("tool", f"{nama_tool} {_ringkas(args)}".rstrip())
                if nama_tool.startswith("mcp_"):
                    server = peta_mcp.get(nama_tool)
                    if server is None:
                        keluaran = "GALAT: server MCP untuk tool ini tidak aktif."
                    else:
                        try:
                            keluaran = mcp_client.panggil(server, nama_tool, args)
                        except mcp_client.GalatMcp as exc:
                            keluaran = f"GALAT MCP: {exc}"
                else:
                    keluaran = agent_tools.jalankan(nama_tool, args, cwd)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or nama_tool,
                        "name": nama_tool,
                        "content": _teks_tool(keluaran),
                    }
                )
            masuk = hasil.usage.get("prompt_tokens", 0)
            keluar = hasil.usage.get("completion_tokens", 0)
            kabar("step", f"langkah {langkah} selesai ({masuk} in / {keluar} out token)")
        else:
            hasil.galat = f"Agent melewati batas {MAKS_LANGKAH} langkah."
    except openai_client.Dibatalkan as exc:
        raise Dibatalkan(str(exc)) from exc
    except openai_client.GalatProvider as exc:
        hasil.galat = exc.pesan
        hasil.ditolak = exc.ditolak
        hasil.batas_waktu = exc.batas_waktu
    except (ValueError, OSError) as exc:
        hasil.galat = str(exc)
    finally:
        hasil.durasi = time.monotonic() - mulai
    return hasil


class Dibatalkan(Exception):
    """Sinyal internal; diterjemahkan pipeline jadi `PipelineDibatalkan`."""


def _ringkas(args: dict) -> str:
    for kunci in ("path", "filePath", "url", "pattern", "name", "machine", "cmd"):
        nilai = args.get(kunci) if isinstance(args, dict) else None
        if isinstance(nilai, str) and nilai:
            return nilai.split("?", 1)[0][-70:]
    return ""
