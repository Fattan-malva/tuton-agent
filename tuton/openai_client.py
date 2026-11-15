"""Klien chat completions untuk endpoint OpenAI-compatible.

Hanya memakai `requests` yang sudah jadi dependensi. Streaming SSE diurai
sendiri supaya teks muncul selama agent bekerja, dan tool call yang datang
sebagai potongan JSON digabung per indeks.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import requests

# Galat yang berarti model/provider ini tidak bisa dipakai sekarang, jadi
# pipeline boleh pindah ke model cadangan. Status lain (400, 500) diperlakukan
# sebagai kegagalan biasa supaya model yang sama dicoba ulang sekali.
_POLA_DITOLAK = re.compile(
    r"usage limit|usage credits|insufficient (?:balance|credit|quota)|"
    r"quota|model (?:is )?not (?:found|available|included)|unauthorized|"
    r"api key|authentication|forbidden|no such model",
    re.IGNORECASE,
)


class GalatProvider(Exception):
    """Kegagalan satu panggilan model, sudah diterjemahkan."""

    def __init__(
        self, pesan: str, *, ditolak: bool = False, batas_waktu: bool = False
    ) -> None:
        super().__init__(pesan)
        self.pesan = pesan
        self.ditolak = ditolak
        self.batas_waktu = batas_waktu


class Dibatalkan(Exception):
    """Job dihentikan pengguna di tengah streaming."""


@dataclass
class HasilChat:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def _headers(api_key: str) -> dict[str, str]:
    out = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        out["Authorization"] = f"Bearer {api_key}"
    return out


def _pesan_dari_body(status: int, body: str) -> str:
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    pesan = ""
    if isinstance(data, dict):
        galat = data.get("error")
        if isinstance(galat, dict):
            pesan = str(galat.get("message") or galat.get("type") or "")
        elif isinstance(galat, str):
            pesan = galat
        pesan = pesan or str(data.get("message") or "")
    return (pesan or body or f"HTTP {status}").strip()[:300]


def _ditolak(status: int, pesan: str) -> bool:
    if status in (401, 403, 404, 429):
        return True
    return bool(_POLA_DITOLAK.search(pesan or ""))


def daftar_model(base_url: str, api_key: str, timeout: int = 20) -> list[str]:
    """`GET /models` untuk tombol tes/ambil model di menu Provider."""
    url = f"{(base_url or '').rstrip('/')}/models"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=(10, timeout))
    except requests.RequestException as exc:
        raise GalatProvider(f"Tidak bisa menghubungi provider: {exc}") from exc
    if r.status_code >= 400:
        pesan = _pesan_dari_body(r.status_code, r.text)
        raise GalatProvider(pesan, ditolak=_ditolak(r.status_code, pesan))
    try:
        data = r.json()
    except ValueError as exc:
        raise GalatProvider("Respons /models bukan JSON.") from exc
    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            nama = item.get("id") or item.get("name")
            if nama:
                out.append(str(nama))
        elif isinstance(item, str):
            out.append(item)
    return list(dict.fromkeys(out))


def _gabung_tool_delta(akumulasi: dict[int, dict], deltas: list) -> None:
    for d in deltas:
        if not isinstance(d, dict):
            continue
        idx = int(d.get("index") or 0)
        slot = akumulasi.setdefault(
            idx,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if d.get("id"):
            slot["id"] = str(d["id"])
        fungsi = d.get("function") or {}
        if isinstance(fungsi, dict):
            if fungsi.get("name"):
                slot["function"]["name"] += str(fungsi["name"])
            if fungsi.get("arguments"):
                slot["function"]["arguments"] += str(fungsi["arguments"])


def _rapikan_tool(akumulasi: dict[int, dict]) -> list[dict]:
    out: list[dict] = []
    for idx in sorted(akumulasi):
        slot = akumulasi[idx]
        if not slot["function"]["name"]:
            continue
        if not slot["id"]:
            slot["id"] = f"call_{idx}"
        out.append(slot)
    return out


def chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    timeout: int = 180,
    batas: float | None = None,
    cancel_event=None,
    on_delta=None,
) -> HasilChat:
    """Satu putaran chat. Melempar `GalatProvider`/`Dibatalkan`."""
    url = f"{(base_url or '').rstrip('/')}/chat/completions"
    body: dict = {"model": model, "messages": messages, "stream": True}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    body["stream_options"] = {"include_usage": True}
    mulai = time.monotonic()

    try:
        r = requests.post(
            url,
            headers=_headers(api_key),
            json=body,
            timeout=(15, timeout),
            stream=True,
        )
    except requests.RequestException as exc:
        raise GalatProvider(f"Gagal menghubungi provider: {exc}") from exc

    if r.status_code >= 400:
        pesan = _pesan_dari_body(r.status_code, r.text)
        raise GalatProvider(pesan, ditolak=_ditolak(r.status_code, pesan))

    hasil = HasilChat()
    akumulasi: dict[int, dict] = {}
    ctype = (r.headers.get("Content-Type") or "").lower()

    # Sebagian endpoint mengabaikan `stream` dan membalas JSON utuh.
    if "event-stream" not in ctype:
        try:
            data = r.json()
        except ValueError as exc:
            raise GalatProvider("Respons provider bukan JSON.") from exc
        pilihan = (data.get("choices") or [{}])[0] or {}
        pesan = pilihan.get("message") or {}
        hasil.content = str(pesan.get("content") or "")
        for d in pesan.get("tool_calls") or []:
            _gabung_tool_delta(akumulasi, [d])
        hasil.tool_calls = _rapikan_tool(akumulasi)
        hasil.usage = data.get("usage") or {}
        return hasil

    try:
        for line in r.iter_lines(decode_unicode=True):
            if cancel_event is not None and cancel_event.is_set():
                raise Dibatalkan("Job dihentikan pengguna.")
            if batas is not None and time.monotonic() - mulai > batas:
                raise GalatProvider(
                    f"Melewati batas waktu {int(batas)} detik.", batas_waktu=True
                )
            if not line:
                continue
            baris = line.strip()
            if baris.startswith("data:"):
                baris = baris[5:].strip()
            if not baris or baris == "[DONE]":
                continue
            try:
                data = json.loads(baris)
            except ValueError:
                continue
            if isinstance(data.get("error"), (dict, str)):
                pesan = _pesan_dari_body(0, json.dumps(data))
                raise GalatProvider(pesan, ditolak=_ditolak(0, pesan))
            usage = data.get("usage")
            if isinstance(usage, dict):
                hasil.usage = usage
            for pilihan in data.get("choices") or []:
                delta = (pilihan or {}).get("delta") or {}
                teks = delta.get("content")
                if isinstance(teks, str) and teks:
                    hasil.content += teks
                    if on_delta is not None:
                        on_delta(teks)
                _gabung_tool_delta(akumulasi, delta.get("tool_calls") or [])
    except requests.RequestException as exc:
        raise GalatProvider(f"Koneksi provider terputus: {exc}") from exc
    finally:
        r.close()

    hasil.tool_calls = _rapikan_tool(akumulasi)
    if not hasil.usage:
        # Perkiraan kasar supaya log tetap punya angka saat provider tidak
        # mengirim usage pada mode streaming.
        hasil.usage = {
            "prompt_tokens": sum(len(str(m.get("content") or "")) for m in messages) // 4,
            "completion_tokens": len(hasil.content) // 4,
        }
    return hasil
