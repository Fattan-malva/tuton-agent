import { Cpu, Globe2, HardDrive, Save, ShieldCheck, UserSquare } from 'lucide-react';
import { useEffect, useState } from 'react';
import apiClient from '../lib/api-client';
import type { AppConfig, ToastType } from '../lib/types';

interface SettingsProps {
  config: AppConfig | null;
  onSaved: () => Promise<void>;
  onNotify: (message: string, type?: ToastType) => void;
}

interface SettingsForm {
  nama: string;
  nim: string;
  prodi: string;
  moodle_session: string;
  moodle_url: string;
  opencode_model: string;
  output_dir: string;
}

const emptyForm: SettingsForm = {
  nama: '',
  nim: '',
  prodi: '',
  moodle_session: '',
  moodle_url: '',
  opencode_model: '',
  output_dir: './output',
};

export default function Settings({ config, onSaved, onNotify }: SettingsProps) {
  const [form, setForm] = useState<SettingsForm>(emptyForm);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setForm({
      nama: config?.nama ?? '',
      nim: config?.nim ?? '',
      prodi: config?.prodi ?? '',
      moodle_session: '',
      moodle_url: config?.base_url ?? '',
      opencode_model: config?.model && config.model !== '(default)' ? config.model : '',
      output_dir: config?.output_dir ?? './output',
    });
  }, [config]);

  const updateField = (field: keyof SettingsForm, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSaving(true);

    try {
      const response = await apiClient.saveConfig(form);
      if (!response.success) throw new Error(response.error || 'Gagal menyimpan settings.');
      onNotify('Settings berhasil disimpan.', 'success');
      await onSaved();
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
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">Atur identitas mahasiswa, sesi Moodle, dan model OpenCode.</p>
      </div>

      <form onSubmit={handleSubmit} className="pixel-panel max-w-4xl p-5 sm:p-7">
        <div className="border-b-2 border-border pb-5 mb-6">
          <div className="flex items-center gap-2 text-text">
            <UserSquare size={17} className="text-accent" aria-hidden="true" />
            <h2 className="font-display text-sm">Data Mahasiswa</h2>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted">Identitas ini digunakan sebagai metadata dokumen jawaban.</p>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="pixel-field">
              <span className="pixel-label">Nama Lengkap</span>
              <input className="pixel-input" name="nama" value={form.nama} onChange={(event) => updateField('nama', event.target.value)} placeholder="Nama lengkap" />
            </label>
            <label className="pixel-field">
              <span className="pixel-label">NIM</span>
              <input className="pixel-input" name="nim" value={form.nim} onChange={(event) => updateField('nim', event.target.value)} placeholder="Nomor induk mahasiswa" />
            </label>
            <label className="pixel-field md:col-span-2">
              <span className="pixel-label">Program Studi (Prodi)</span>
              <input className="pixel-input" name="prodi" value={form.prodi} onChange={(event) => updateField('prodi', event.target.value)} placeholder="Program studi" />
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
            <label className="pixel-field">
              <span className="pixel-label">OpenCode Model</span>
              <input className="pixel-input font-terminal" name="opencode_model" value={form.opencode_model} onChange={(event) => updateField('opencode_model', event.target.value)} placeholder="opencode/big-pickle" />
            </label>
            <label className="pixel-field">
              <span className="pixel-label">Output Directory</span>
              <input className="pixel-input pixel-input-readonly font-terminal" name="output_dir" value={form.output_dir} readOnly />
            </label>
          </div>
          <div className="mt-4 flex items-center gap-2 text-xs text-muted">
            <ShieldCheck size={15} className="text-success" aria-hidden="true" />
            <HardDrive size={14} className="text-muted" aria-hidden="true" />
            <span>Hasil agent tetap disimpan di folder output backend.</span>
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
