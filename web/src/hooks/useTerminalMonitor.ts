import { useCallback, useEffect, useRef, useState } from 'react';
import apiClient from '../lib/api-client';

export interface TerminalSnapshot {
  output: string[];
  running: boolean;
  returncode: number | null;
  elapsed: number;
  progress: number;
  step: string;
  label: string;
  done: number;
  total: number;
}

const initialSnapshot: TerminalSnapshot = {
  output: [],
  running: false,
  returncode: null,
  elapsed: 0,
  progress: 0,
  step: 'idle',
  label: 'Menyiapkan...',
  done: 0,
  total: 0,
};

interface ProgressState {
  course: string;
  done: number;
  total: number;
  partial: number;
  step: string;
  item: string;
  kind: string;
}

function progressFor(progress: ProgressState): number {
  if (progress.step === 'selesai') return 100;
  if (progress.total <= 0) return 0;
  return Math.min(100, Math.round(((progress.done + progress.partial) / progress.total) * 100));
}

function parseProgress(lines: string[]): Omit<TerminalSnapshot, 'output' | 'running' | 'returncode' | 'elapsed'> {
  const progress: ProgressState = {
    course: '',
    done: 0,
    total: 0,
    partial: 0,
    step: 'idle',
    item: '',
    kind: '',
  };

  for (const line of lines) {
    const courseMatch = line.match(/^=== (.+) ===$/);
    if (courseMatch) {
      progress.course = courseMatch[1].replace(/\s+\(form soal\)\s*$/, '').trim();
      progress.total = 0;
      progress.done = 0;
      progress.step = 'scraping';
    }

    const totalMatch = line.match(/TOTAL:\s*(\d+)\s*item/i);
    if (totalMatch) progress.total = Number(totalMatch[1]);
    if (progress.total <= 0) progress.total = 1;

    const itemMatch = line.match(/\[\s*(\d+)\s*\/\s*(\d+)\s*\]\s*\[(diskusi|tugas)\]\s+(.+?)\s+→/);
    if (itemMatch) {
      progress.total = Number(itemMatch[2]);
      progress.done = Math.max(0, Number(itemMatch[1]) - 1);
      progress.kind = itemMatch[3];
      progress.item = itemMatch[4].trim();
      progress.partial = line.includes('transkripsi')
        ? 0.35
        : line.includes('opencode')
          ? 0.7
          : line.includes('docx')
            ? 0.92
            : 0;
      progress.step = line.includes('transkripsi')
        ? 'transkripsi'
        : line.includes('opencode')
          ? 'opencode'
          : line.includes('docx')
            ? 'docx'
            : 'mengerjakan';
    }

    if (/→ sudah dikerjakan, dilewati/.test(line)) {
      progress.done += 1;
      progress.step = 'mengerjakan';
    }

    if (/^\s*· Transkripsi /.test(line)) progress.step = 'transkripsi';
    if (/→ .*? run \.\.\./.test(line)) progress.step = 'opencode';
    if (/✓ .+? siap\.$/.test(line)) {
      progress.done += 1;
      progress.partial = 0;
      progress.step = 'docx';
    }
    if (/Selesai\. (\d+) item diproses/.test(line)) {
      progress.done = Number(line.match(/Selesai\. (\d+) item diproses/)?.[1] ?? 0);
      progress.step = 'selesai';
    }
    if (/✗ Gagal|ERROR|timeout|BERHENTI|Soal kosong/i.test(line)) progress.step = 'error';
  }

  return {
    progress: progressFor(progress),
    step: progress.step,
    label: progress.course || 'Menyiapkan...',
    done: progress.done,
    total: progress.total,
  };
}

/**
 * Monitor jalannya proses `python main.py` di server (run agent / form soal).
 *
 * Polling berjalan terus-menerus selama aplikasi terbuka, sehingga proses
 * TIDAK berhenti / hilang dari layar saat user pindah-pindah menu. onComplete
 * hanya dipanggil bila sebuah proses benar-benar sempat terlihat berjalan,
 * lalu selesai (tidak langsung dipanggil saat idle). `reset()` dipanggil
 * setiap akan memulai run baru dan meng-aktifkan ulang deteksi selesai.
 */
export function useTerminalMonitor(active = true, onComplete?: (returncode: number) => void) {
  const [output, setOutput] = useState<string[]>([]);
  const [snapshot, setSnapshot] = useState<TerminalSnapshot>(initialSnapshot);
  const [token, setToken] = useState(0);
  const onCompleteRef = useRef(onComplete);
  const completedRef = useRef(false);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!active) return;

    let cancelled = false;
    let started = false;
    completedRef.current = false;

    const poll = async () => {
      try {
        const [status, nextOutput] = await Promise.all([
          apiClient.getRunStatus(),
          apiClient.getRunOutput(),
        ]);

        if (cancelled) return;

        const lines = nextOutput.output ?? [];
        const parsed = parseProgress(lines);
        setOutput(lines);
        setSnapshot({
          ...parsed,
          output: lines,
          running: status.running,
          returncode: status.returncode,
          elapsed: status.elapsed ?? 0,
        });

        if (status.running) started = true;

        if (!status.running && started && !completedRef.current && onCompleteRef.current) {
          completedRef.current = true;
          onCompleteRef.current(status.returncode ?? 0);
        }
      } catch {
        if (!cancelled) {
          setSnapshot((current) => ({
            ...current,
            running: false,
            step: 'error',
            label: 'Koneksi terminal terputus',
          }));
        }
      }
    };

    void poll();
    const interval = window.setInterval(() => void poll(), 1000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [active, token]);

  const reset = useCallback(() => {
    setOutput([]);
    setSnapshot(initialSnapshot);
    setToken((current) => current + 1);
  }, []);

  return { output, snapshot, reset };
}