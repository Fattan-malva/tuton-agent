import { useState } from 'react';
import { Navigation } from '../components/Navigation';
import { StatusPanel } from '../components/StatusPanel';
import { ResultsPanel } from '../components/ResultsPanel';
import { RunPanel } from '../components/RunPanel';
import { SettingsPanel } from '../components/SettingsPanel';

export default function HomePage() {
  const [currentTab, setCurrentTab] = useState('status');

  return (
    <div className="flex h-screen bg-primary">
      <Navigation />
      <main className="flex-1 overflow-auto">
        <StatusPanel />
        <ResultsPanel />
        <RunPanel />
        <SettingsPanel />
      </main>
    </div>
  );
}