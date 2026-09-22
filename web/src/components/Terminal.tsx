import { Square, Trash2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { TerminalSnapshot } from '../hooks/useTerminalMonitor';

export interface TerminalViewProps {
  output: string[];
  snapshot: TerminalSnapshot;
  command: string;
  onStop: () => void;
  onClear: () => void;
  busy: boolean;
}

export interface TerminalController {
  output: string[];
  snapshot: TerminalSnapshot;
  command: string;
  setCommand: (command: string) => void;
  reset: () => void;
  onStopRequested: () => void;
  onClearTerminal: () => void;
}

function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  const pad = (value: number) => String(value).padStart(2, '0');
  return hours > 0 ? `${pad(hours)}:${pad(minutes)}:${pad(remainder)}` : `${pad(minutes)}:${pad(remainder)}`;
}

function lineTone(line: string): string {
  if (/ERROR|Gagal|✗|exit code/i.test(line)) return 'error';
  if (/✓|Selesai|siap\.$/i.test(line)) return 'success';
  if (/dilewati|timeout|BERHENTI|Soal kosong|warning/i.test(line)) return 'warning';
  if (/^user@tuton/.test(line)) return 'cmd';
  return 'info';
}

export default function Terminal({ output, snapshot, command, onStop, onClear, busy }: TerminalViewProps) {
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const terminal = terminalRef.current;
    if (terminal) terminal.scrollTop = terminal.scrollHeight;
  }, [output]);

  const isRunning = snapshot.running;
  const progress = snapshot.progress;
  const activeProgress = ['scraping', 'mengerjakan', 'transkripsi', 'opencode', 'docx'].includes(snapshot.step);

  return (
    <div className="pixel-terminal-panel min-h-[340px] overflow-hidden">
      <div className="flex items-center justify-between border-b-2 border-border bg-panel-strong px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="pixel-terminal-dot pixel-terminal-dot-danger" />
          <span className="pixel-terminal-dot pixel-terminal-dot-warning" />
          <span className="pixel-terminal-dot pixel-terminal-dot-success" />
          {isRunning && <span className="pixel-running-label"><span className="pixel-online-dot" /> Running</span>}
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onStop} disabled={!isRunning} className="pixel-terminal-action text-danger">
            <Square size={12} fill="currentColor" aria-hidden="true" /> stop
          </button>
          <button type="button" onClick={onClear} className="pixel-terminal-action text-muted hover:text-text">
            <Trash2 size={13} aria-hidden="true" /> clear
          </button>
        </div>
      </div>

      {(busy || progress > 0 || command) && (
        <div className="border-b-2 border-border bg-panel px-4 py-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="truncate font-terminal text-[10px] text-text">{snapshot.label}</span>
            <span className="shrink-0 font-terminal text-[10px] text-muted">{snapshot.done}/{snapshot.total || '?'}</span>
          </div>
          <div className="pixel-progress" aria-label={`Progress ${progress}%`}>
            <div className="pixel-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-2 flex items-center justify-between font-terminal text-[9px] uppercase tracking-[0.1em] text-muted">
            <span>{activeProgress ? snapshot.step : snapshot.step}</span>
            <span>{formatElapsed(snapshot.elapsed)}</span>
          </div>
        </div>
      )}

      <div ref={terminalRef} className="pixel-terminal-scroll" aria-live="polite">
        {command && <div className="pixel-terminal-line pixel-terminal-cmd">{command}</div>}
        {output.length === 0 && !command ? (
          <div className="pixel-terminal-empty">
            <span className="text-success">$</span>
            <span>Sistem siap menerima perintah.</span>
          </div>
        ) : output.map((line, index) => (
          <div key={`${index}-${line}`} className={`pixel-terminal-line pixel-terminal-${lineTone(line)}`}>{line || ' '}</div>
        ))}
      </div>
    </div>
  );
}