import React from 'react';

const Navigation = () => {
  const [currentTab, setCurrentTab] = React.useState('status');

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-full bg-surface/80 backdrop-blur-xl border-b border-white/5">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-accent to-purple-500 rounded-xl flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 12h6M15 12h6"/></svg>
          </div>
          <span className="text-xl font-bold text-white">Tuton Agent</span>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={() => setCurrentTab('status')} className="nav-link active">
            <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7l5 5m0 0l-5 5M7 20h10a2 2 0 002-2V8a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
            </button>
            <button onClick={() => setCurrentTab('results')} className="nav-link">
              <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 13l-7 7-7-7"/></svg>
            </button>
            <button onClick={() => setCurrentTab('run')} className="nav-link">
              <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 4-3 4"/></svg>
            </button>
            <button onClick={() => setCurrentTab('settings')} className="nav-link">
              <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 20h5v-2H5v2zm4-6h5V6H9v2zm1-4h5V6H9v2zm1-4h5V6H9v2z"/></svg>
            </button>
          </div>
        </div>
      </nav>
    </nav>
  );
};

export default Navigation;