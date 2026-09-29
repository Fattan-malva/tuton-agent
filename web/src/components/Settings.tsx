import { Cpu, Globe2, HardDrive, RefreshCw, Save, Search, ShieldCheck, UserSquare } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import apiClient from '../lib/api-client';
import type { AppConfig, ModelGroup, ToastType } from '../lib/types';

interface SettingsProps {
  config: AppConfig | null;
  onSaved: () => Promise<void>;
  onNotify: (message: string, type?: ToastType) => void;
}

interface SettingsForm {
  nama: string;
  nim: string;
  prodi: string;
  semester: string;
  ut_daerah: string;
  moodle_session: string;
  moodle_url: string;
  opencode_model: string;
  /** Model agen pembantu. Kosong = auto-pilih + uji dulu (lihat generator/models.py). */
  opencode_model_helper: string;
  /**
   * Model vision untuk transkripsi lampiran. Kosong = auto-pilih dari
   * `opencode models` (perilaku bawaan, tidak berubah).
   */
  opencode_model_transcribe: string;
  output_dir: string;
  jobs: string;
  max_pustaka: string;
}

/** Batas keras daftar pustaka. Di-hardcode di UI supaya form tidak pernah
 *  mengirim angka absurd yang hanya akan ditolak server. */
const DEFAULT_MAX_PUSTAKA = 5;

const emptyForm: SettingsForm = {
  nama: '',
  nim: '',
  prodi: '',
  semester: '',
  ut_daerah: '',
  moodle_session: '',
  moodle_url: '',
  opencode_model: '',
  opencode_model_helper: '',
  opencode_model_transcribe: '',
  output_dir: './output',
  jobs: '2',
  max_pustaka: String(DEFAULT_MAX_PUSTAKA),
};

interface ModelPickerProps {
  value: string;
  groups: ModelGroup[];
  loading: boolean;
  total: number;
  defaultModel: string;
  onChange: (value: string) => void;
  onRefresh: () => void;
  /** Label di atas input. Bawaan = model penulis. */
  label?: string;
  /** `name` input + suffix `id` listbox, supaya dua picker tidak bentrok. */
  idSuffix?: string;
  /** Teks tombol "Bawaan opencode"; null menyembunyikannya. */
  defaultOptionLabel?: string | null;
  /** Nilai saat opsi bawaan dipilih. Default = `defaultModel`. */
  defaultOptionValue?: string;
  /** Placeholder saat nilai kosong. */
  emptyHint?: string;
  /**
   * Teks kecil di bawah input. Bawaan untuk model penulis; picker transkripsi
   * perlu kalimat sendiri karena model vision bukan untuk menjawab soal.
   */
  hint?: string;
}

/**
 * Pemilih model opencode.
 *
 * Daftar model opencode bisa 400+ entri, jadi `<select>` biasa tidak praktis.
 * Komponen ini menggabungkan input pencarian dengan daftar bergrup per provider,
 * plus opsi "pakai default opencode" supaya pilihan awal tetap big-pickle.
 */
function ModelPicker({
  value,
  groups,
  loading,
  total,
  defaultModel,
  onChange,
  onRefresh,
  label = 'Model OpenCode untuk Mengerjakan',
  idSuffix = 'writer',
  defaultOptionLabel = 'Bawaan opencode',
  defaultOptionValue,
  emptyHint,
  hint,
}: ModelPickerProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return groups;
    return groups
      .map((group) => ({
        provider: group.provider,
        models: group.models.filter(
          (model) =>
            model.id.toLowerCase().includes(needle) ||
            group.provider.toLowerCase().includes(needle),
        ),
      }))
      .filter((group) => group.models.length > 0);
  }, [groups, query]);

  const flat = useMemo(() => visible.flatMap((group) => group.models), [visible]);

  useEffect(() => {
    setHighlight(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const pick = (modelId: string) => {
    onChange(modelId);
    setQuery('');
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      setHighlight((current) => {
        const next = current + delta;
        if (next < 0) return flat.length - 1;
        if (next >= flat.length) return 0;
        return next;
      });
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const chosen = flat[highlight];
      if (open && chosen) pick(chosen.id);
      return;
    }
    if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  const matched = flat.length;
  const listboxId = `model-listbox-${idSuffix}`;

  return (
    <div className="md:col-span-2">
      <span className="pixel-label">{label}</span>

      <div ref={wrapRef} className="relative mt-1">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
              aria-hidden="true"
            />
            <input
              // Padding kiri WAJIB lewat `pixel-input-icon`, bukan utility
              // Tailwind seperti `pl-8`. Class `pixel-*` ditulis di luar
              // `@layer`, dan di CSS kaskade aturan tanpa layer selalu menang
              // atas utility yang Berlapis -- jadi `pl-8` diam-diam diabaikan
              // dan teks menabrak ikon. `pixel-input-icon` yang mengaturnya
              // (38px), jadi ada ruang lega untuk ikon 16px di `left-3`.
              className="pixel-input pixel-input-icon font-terminal"
              name={`opencode_model_${idSuffix}`}
              value={open ? query : value}
              placeholder={value || emptyHint || defaultModel}
              autoComplete="off"
              role="combobox"
              aria-expanded={open}
              aria-controls={listboxId}
              aria-autocomplete="list"
              onFocus={() => setOpen(true)}
              onChange={(event) => {
                setQuery(event.target.value);
                setOpen(true);
              }}
              onKeyDown={onKeyDown}
            />
          </div>
          <button
            type="button"
            className="pixel-button pixel-button-secondary shrink-0 px-2.5"
            onClick={onRefresh}
            disabled={loading}
            title="Muat ulang daftar model dari opencode"
          >
            {loading ? (
              <span className="pixel-spinner" aria-hidden="true" />
            ) : (
              <RefreshCw size={15} aria-hidden="true" />
            )}
            <span className="sr-only">Muat ulang daftar model</span>
          </button>
        </div>

        {open && (
          <div
            id={listboxId}
            role="listbox"
            className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto border-2 border-border bg-panel shadow-[4px_4px_0_rgba(0,0,0,0.35)]"
          >
            {defaultOptionLabel !== null && (
              <button
                type="button"
                role="option"
                aria-selected={value === (defaultOptionValue ?? defaultModel)}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left font-terminal text-xs hover:bg-accent/15"
                onClick={() => pick(defaultOptionValue ?? defaultModel)}
              >
                <span>{defaultOptionLabel}</span>
                <span className="text-muted">
                  {defaultOptionValue === '' ? '—' : defaultModel}
                </span>
              </button>
            )}
            <div className="border-t-2 border-border" />

            {loading && matched === 0 && (
              <p className="px-3 py-3 font-terminal text-xs text-muted">
                Memuat daftar model...
              </p>
            )}

            {!loading && matched === 0 && (
              <p className="px-3 py-3 font-terminal text-xs text-muted">
                Tidak ada model yang cocok. Tekan RefreshCw untuk memuat ulang.
              </p>
            )}

            {visible.map((group) => (
              <div key={group.provider}>
                <p className="bg-surface px-3 py-1 font-terminal text-[10px] uppercase tracking-[0.16em] text-muted">
                  {group.provider} ({group.models.length})
                </p>
                {group.models.map((model) => {
                  const index = flat.findIndex((item) => item.id === model.id);
                  const selected = value === model.id;
                  return (
                    <button
                      key={model.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`flex w-full items-center gap-2 px-3 py-1.5 text-left font-terminal text-xs hover:bg-accent/15 ${
                        index === highlight ? 'bg-accent/10' : ''
                      } ${selected ? 'text-accent' : 'text-text'}`}
                      onClick={() => pick(model.id)}
                      onMouseEnter={() => setHighlight(index)}
                    >
                      <span className="min-w-0 flex-1 truncate">{model.id}</span>
                      {selected && <span className="shrink-0 text-[10px]">AKTIF</span>}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </div>

      <span className="pixel-helper">
        {loading
          ? 'Memuat daftar model dari opencode...'
          : hint ??
            `${matched} dari ${total} model ditampilkan. Model dipakai agent saat menjawab, bukan untuk transkripsi lampiran (itu memakai model vision terpisah).`}
      </span>
    </div>
  );
}

export default function Settings({ config, onSaved, onNotify }: SettingsProps) {
  const [form, setForm] = useState<SettingsForm>(emptyForm);
  const [isSaving, setIsSaving] = useState(false);
  const [modelGroups, setModelGroups] = useState<ModelGroup[]>([]);
  const [modelTotal, setModelTotal] = useState(0);
  const [modelLoading, setModelLoading] = useState(true);
  const defaultModel = config?.default_model ?? 'opencode/big-pickle';

  const loadModels = useCallback(async (refresh: boolean) => {
    setModelLoading(true);
    try {
      const response = await apiClient.getModels({ refresh });
      setModelGroups(response.groups ?? []);
      setModelTotal(response.total ?? 0);
    } catch (caught) {
      setModelGroups([]);
      setModelTotal(0);
      onNotify(
        caught instanceof Error
          ? `Gagal memuat daftar model: ${caught.message}`
          : 'Gagal memuat daftar model.',
        'warning',
      );
    } finally {
      setModelLoading(false);
    }
  }, [onNotify]);

  useEffect(() => {
    void loadModels(false);
  }, [loadModels]);

  useEffect(() => {
    const runtime = config?.runtime;
    setForm({
      nama: config?.nama ?? '',
      nim: config?.nim ?? '',
      prodi: config?.prodi ?? '',
      semester: config?.semester ?? '',
      ut_daerah: config?.ut_daerah ?? '',
      moodle_session: '',
      moodle_url: config?.base_url ?? '',
      opencode_model: config?.model && config.model !== '(default)' ? config.model : '',
      // WAJIB `helper_model_configured` (nilai yang tersimpan di .env), bukan
      // `runtime.helper_model` (hasil auto-pilih). Kalau yang latter dipakai,
      // model auto-pilih ikut tersimpan begitu form dikirim -- jadi model yang
      // tadinya "otomatis" terkunci jadi manual tanpa pernah disentuh user.
      // Kosong = otomatis, dan itu yang harus tampil saat field di .env kosong.
      opencode_model_helper: config?.helper_model_configured ?? '',
      // Sama seperti helper: WAJIB nilai yang tersimpan di .env, bukan model
      // hasil auto-pilih, supaya auto-pick tidak ikut ter-save sebagai
      // pilihan manual begitu form dikirim.
      opencode_model_transcribe: config?.transcribe_model_configured ?? '',
      output_dir: config?.output_dir ?? './output',
      jobs: String(runtime?.jobs ?? 2),
      max_pustaka: String(runtime?.max_pustaka ?? DEFAULT_MAX_PUSTAKA),
    });
  }, [config]);

  const updateField = <K extends keyof SettingsForm>(field: K, value: SettingsForm[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSaving(true);

    // Field angka dikirim sebagai string dari `<input type="number">`. Server
    // mem-parsing sendiri (dan memakai nilai lama kalau tidak terbaca), jadi
    // tidak perlu konversi di sini -- konversi diam-diam justru menyembunyikan
    // input yang tidak valid.
    try {
      const response = await apiClient.saveConfig(form);
      if (!response.success) throw new Error(response.error || 'Gagal menyimpan settings.');
      onNotify('Settings berhasil disimpan.', 'success');
      await onSaved();
      void loadModels(true);
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal menyimpan settings.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section aria-labelledby="settings-heading">
      <div className="mb-6 max-w-3xl">
        <div className="font-terminal text-[10px] uppercase tracking-[0.18em] text-accent">Control Room</div>
        <h1 id="settings-heading" className="mt-1 font-display text-2xl leading-snug text-text sm:text-3xl">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Atur identitas mahasiswa, sesi Moodle, dan model OpenCode.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="pixel-panel max-w-4xl p-5 sm:p-7">
        <div className="border-b-2 border-border pb-5 mb-6">
          <div className="flex items-center gap-2 text-text">
            <UserSquare size={17} className="text-accent" aria-hidden="true" />
            <h2 className="font-display text-sm">Data Mahasiswa</h2>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            Identitas ini menjadi tabel identitas di halaman pertama setiap dokumen
            jawaban. Baris yang dikosongkan tidak dicetak, jadi Prodi boleh kosong
            selama tidak dipakai di template Anda.
          </p>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="pixel-field">
              <span className="pixel-label">Nama Lengkap</span>
              <input className="pixel-input" name="nama" value={form.nama} onChange={(event) => updateField('nama', event.target.value)} placeholder="Nama lengkap" />
            </label>
            <label className="pixel-field">
              <span className="pixel-label">NIM</span>
              <input className="pixel-input" name="nim" value={form.nim} onChange={(event) => updateField('nim', event.target.value)} placeholder="Nomor induk mahasiswa" />
            </label>
            <label className="pixel-field">
              <span className="pixel-label">Program Studi (Prodi)</span>
              <input className="pixel-input" name="prodi" value={form.prodi} onChange={(event) => updateField('prodi', event.target.value)} placeholder="Program studi" />
            </label>
            <label className="pixel-field">
              <span className="pixel-label">Semester</span>
              <input
                className="pixel-input"
                name="semester"
                value={form.semester}
                onChange={(event) => updateField('semester', event.target.value)}
                placeholder="Semester 2"
              />
              <span className="pixel-helper">Boleh kosong. Tulis “Semester 2”, bukan cuma “2”.</span>
            </label>
            <label className="pixel-field md:col-span-2">
              <span className="pixel-label">UT Daerah</span>
              <input
                className="pixel-input"
                name="ut_daerah"
                value={form.ut_daerah}
                onChange={(event) => updateField('ut_daerah', event.target.value)}
                placeholder="Jakarta"
              />
              <span className="pixel-helper">
                Nama UT tempat ujian, bukan nama lengkap universitas. Boleh kosong.
              </span>
            </label>
          </div>
        </div>

        <div className="border-b-2 border-border pb-5 mb-6">
          <div className="flex items-center gap-2 text-text">
            <Globe2 size={17} className="text-accent" aria-hidden="true" />
            <h2 className="font-display text-sm">Kredensial Moodle</h2>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted">Sesi Moodle disimpan terpisah dari file environment server.</p>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="pixel-field md:col-span-2">
              <span className="pixel-label">Moodle Cookie (MoodleSession)</span>
              <input
                className="pixel-input font-terminal"
                name="moodle_session"
                value={form.moodle_session}
                onChange={(event) => updateField('moodle_session', event.target.value)}
                placeholder="MoodleSession=..."
                autoComplete="off"
              />
              <span className="pixel-helper">Disimpan ke moodle_credentials.json dan langsung digunakan tanpa restart.</span>
            </label>
            <label className="pixel-field md:col-span-2">
              <span className="pixel-label">Moodle URL</span>
              <input className="pixel-input font-terminal" name="moodle_url" type="url" value={form.moodle_url} onChange={(event) => updateField('moodle_url', event.target.value)} placeholder="https://elearning.ut.ac.id" />
            </label>
          </div>
        </div>

        <div className="mb-7">
          <div className="flex items-center gap-2 text-text">
            <Cpu size={17} className="text-accent" aria-hidden="true" />
            <h2 className="font-display text-sm">Model Configuration</h2>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <ModelPicker
              value={form.opencode_model}
              groups={modelGroups}
              loading={modelLoading}
              total={modelTotal}
              defaultModel={defaultModel}
              onChange={(value) => updateField('opencode_model', value)}
              onRefresh={() => void loadModels(true)}
            />
            <div className="md:col-span-2">
              <ModelPicker
                value={form.opencode_model_helper}
                groups={modelGroups}
                loading={modelLoading}
                total={modelTotal}
                defaultModel={defaultModel}
                onChange={(value) => updateField('opencode_model_helper', value)}
                onRefresh={() => void loadModels(true)}
                label="Model OpenCode untuk Pembantu (peta soal & daftar pustaka)"
                idSuffix="helper"
                defaultOptionLabel="Pilih otomatis (diuji satu per satu)"
                // Kosongkan field, bukan diisi model default penulis: "otomatis"
                // berarti membiarkan generator/models.py memilih. Mengisi
                // `defaultModel` di sini akan memaksa model penulis jadi model
                // pembantu -- mahal, dan bukan yang jobless clicked.
                defaultOptionValue=""
                emptyHint="pilih otomatis"
              />
              <span className="pixel-helper">
                Dipakai langsung setelah disimpan, untuk memetakan soal dan mencari
                daftar pustaka. Kosongkan agar sistem memilih model opencode zen
                termurah yang benar-benar merespons.
              </span>
            </div>
            <label className="pixel-field">
              <span className="pixel-label">Output Directory</span>
              <input className="pixel-input pixel-input-readonly font-terminal" name="output_dir" value={form.output_dir} readOnly />
            </label>
            <label className="pixel-field">
              <span className="pixel-label">Item Bersamaan (--jobs)</span>
              <input
                className="pixel-input font-terminal"
                name="jobs"
                type="number"
                min={1}
                max={8}
                value={form.jobs}
                onChange={(event) => updateField('jobs', event.target.value)}
              />
              <span className="pixel-helper">
                Tiap item = 1 proses opencode. Naikkan untuk lebih cepat, turunkan
                bila sering kena rate limit.
              </span>
            </label>
            <label className="pixel-field">
              <span className="pixel-label">Maksimum Daftar Pustaka</span>
              <input
                className="pixel-input font-terminal"
                name="max_pustaka"
                type="number"
                min={1}
                max={20}
                value={form.max_pustaka}
                onChange={(event) => updateField('max_pustaka', event.target.value)}
              />
              <span className="pixel-helper">
                Batas keras jumlah referensi per jawaban. Ini batas biaya: tiap
                entri berarti satu kali verifikasi sumber. Bawaan {DEFAULT_MAX_PUSTAKA}.
              </span>
            </label>
            <div className="md:col-span-2">
              <ModelPicker
                value={form.opencode_model_transcribe}
                groups={modelGroups}
                loading={modelLoading}
                total={modelTotal}
                defaultModel={defaultModel}
                onChange={(value) => updateField('opencode_model_transcribe', value)}
                onRefresh={() => void loadModels(true)}
                label="Model OpenCode untuk Transkripsi Lampiran (vision)"
                idSuffix="transcribe"
                defaultOptionLabel="Pilih otomatis (model vision)"
                // Kosongkan field, bukan diisi model default: "otomatis" berarti
                // membiarkan `moodle/transcribe.py` memilih model vision sendiri.
                defaultOptionValue=""
                emptyHint="pilih otomatis"
                hint={`${modelTotal} model terdaftar. Yang benar-benar dipakai hanya yang bisa melihat gambar; kalau model di atas tidak cocok, kandidat vision lain tetap dicoba secara otomatis.`}
              />
              <span className="pixel-helper">
                Dipakai hanya untuk membaca lampiran gambar atau PDF hasil scan
                (tulisan tangan). PDF ber-teks-layer dan dokumen .docx/.xlsx
                dibaca langsung tanpa model sama sekali. Model yang dipilih hanya
                dicoba lebih dulu, bukan dikunci — bila tidak bisa melihat gambar,
                kandidat otomatis berikutnya tetap dipakai. Mengganti model akan
                mentranskripsi ulang lampiran, karena transkrip cache milik model
                lama tidak lagi dipakai.
              </span>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 text-xs text-muted">
            <ShieldCheck size={15} className="text-success" aria-hidden="true" />
            <HardDrive size={14} className="text-muted" aria-hidden="true" />
            <span>
              Pipeline berjalan sebagai proses terpisah, jadi perubahan baru
              berlaku saat run berikutnya dimulai.
            </span>
          </div>
        </div>

        <div className="flex justify-end border-t-2 border-border pt-5">
          <button type="submit" disabled={isSaving} className="pixel-button pixel-button-primary">
            {isSaving ? (
              <>
                <span className="pixel-spinner" aria-hidden="true" />
                <span>Menyimpan...</span>
              </>
            ) : (
              <>
                <Save size={17} aria-hidden="true" />
                <span>Simpan Settings</span>
              </>
            )}
          </button>
        </div>
      </form>
    </section>
  );
}
