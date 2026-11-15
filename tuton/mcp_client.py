"""Klien MCP remote (streamable HTTP) untuk tool tambahan agent.

Hanya transport remote yang didukung: server lokal (`command`) belum perlu --
InstaBox dan server lain yang dipakai proyek ini sudah berupa URL. Tambahkan
transport stdio kalau nanti benar-benar ada server lokal yang wajib dipakai.
"""

from __future__ import annotations

import json
import re
import threading

import requests

_PROTOKOL = "2025-06-18"
_seq = 0
_seq_lock = threading.Lock()


class GalatMcp(Exception):
    pass


def _id() -> int:
    global _seq
    with _seq_lock:
        _seq += 1
        return _seq


def _headers(server: dict, session: str = "", protokol: str = "") -> dict:
    out = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    for k, v in (server.get("headers") or {}).items():
        if k and v:
            out[str(k)] = str(v)
    if session:
        out["Mcp-Session-Id"] = session
    if protokol:
        out["MCP-Protocol-Version"] = protokol
    return out


def _baca_respons(r: requests.Response) -> dict:
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "event-stream" not in ctype:
        try:
            return r.json()
        except ValueError as exc:
            raise GalatMcp(f"Respons MCP bukan JSON: {r.text[:200]}") from exc
    hasil: dict = {}
    for line in r.text.splitlines():
        baris = line.strip()
        if baris.startswith("data:"):
            baris = baris[5:].strip()
        if not baris:
            continue
        try:
            data = json.loads(baris)
        except ValueError:
            continue
        if isinstance(data, dict) and ("result" in data or "error" in data):
            hasil = data
    if not hasil:
        raise GalatMcp("Respons MCP kosong.")
    return hasil


def _rpc(
    server: dict,
    method: str,
    params: dict | None,
    *,
    session: str = "",
    protokol: str = "",
    notifikasi: bool = False,
    timeout: int = 30,
) -> tuple[dict, str]:
    payload: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if not notifikasi:
        payload["id"] = _id()
    try:
        r = requests.post(
            server["url"],
            headers=_headers(server, session, protokol),
            json=payload,
            timeout=(10, timeout),
        )
    except requests.RequestException as exc:
        raise GalatMcp(f"Gagal menghubungi MCP: {exc}") from exc
    if r.status_code >= 400:
        raise GalatMcp(f"HTTP {r.status_code}: {r.text[:250]}")
    session = r.headers.get("Mcp-Session-Id") or session
    if notifikasi or r.status_code == 202 or not (r.text or "").strip():
        return {}, session
    data = _baca_respons(r)
    if isinstance(data.get("error"), dict):
        raise GalatMcp(str(data["error"].get("message") or data["error"]))
    hasil = data.get("result")
    return (hasil if isinstance(hasil, dict) else {}), session


def _siapkan(server: dict, timeout: int = 30) -> tuple[str, str]:
    hasil, session = _rpc(
        server,
        "initialize",
        {
            "protocolVersion": _PROTOKOL,
            "capabilities": {},
            "clientInfo": {"name": "tuton-agent", "version": "1.0"},
        },
        timeout=timeout,
    )
    protokol = str(hasil.get("protocolVersion") or _PROTOKOL)
    _rpc(
        server,
        "notifications/initialized",
        None,
        session=session,
        protokol=protokol,
        notifikasi=True,
        timeout=timeout,
    )
    return session, protokol


def daftar_tool(server: dict, timeout: int = 30) -> list[dict]:
    session, protokol = _siapkan(server, timeout)
    hasil, _ = _rpc(
        server, "tools/list", {}, session=session, protokol=protokol, timeout=timeout
    )
    tools = hasil.get("tools")
    return [t for t in tools if isinstance(t, dict)] if isinstance(tools, list) else []


def _nama_fungsi(kode_server: str, nama: str) -> str:
    bersih = re.sub(r"[^A-Za-z0-9_-]+", "_", f"mcp_{kode_server}_{nama}")
    return bersih[:64]


def tools_untuk(server: dict) -> list[dict]:
    """Definisi function-calling untuk satu server, sesuai filter `tools`."""
    sid = str(server.get("id") or "")
    izin = server.get("tools") or []
    out: list[dict] = []
    try:
        daftar = daftar_tool(server)
    except GalatMcp:
        return out
    for tool in daftar:
        nama = str(tool.get("name") or "")
        if not nama or (izin and nama not in izin):
            continue
        skema = tool.get("inputSchema")
        if not isinstance(skema, dict):
            skema = {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": _nama_fungsi(sid, nama),
                    "description": str(tool.get("description") or "")[:500],
                    "parameters": skema,
                },
            }
        )
    return out


def panggil(server: dict, nama_fungsi: str, args: dict) -> str:
    """Panggil tool berdasarkan nama fungsi yang sudah dipetakan."""
    awal = f"mcp_{server.get('id')}_"
    if not nama_fungsi.startswith(awal):
        raise GalatMcp("Nama tool MCP tidak dikenal.")
    nama = nama_fungsi[len(awal):]
    session, protokol = _siapkan(server)
    hasil, _ = _rpc(
        server,
        "tools/call",
        {"name": nama, "arguments": args if isinstance(args, dict) else {}},
        session=session,
        protokol=protokol,
        timeout=120,
    )
    bagian = hasil.get("content")
    teks: list[str] = []
    if isinstance(bagian, list):
        for item in bagian:
            if isinstance(item, dict) and item.get("type") == "text":
                teks.append(str(item.get("text") or ""))
    if not teks and hasil.get("structuredContent") is not None:
        teks.append(json.dumps(hasil["structuredContent"], ensure_ascii=False))
    if hasil.get("isError"):
        return "GALAT MCP: " + ("\n".join(teks) or "tanpa pesan")
    return "\n".join(teks) or "(tool MCP tidak mengembalikan teks)"
