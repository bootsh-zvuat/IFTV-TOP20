import { NavLink, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import EventsPage from './pages/EventsPage';
import ScenarioPage from './pages/ScenarioPage';
import ComparePage from './pages/ComparePage';
import SettingsPage from './pages/SettingsPage';
import SavesPage from './pages/SavesPage';

const navCls = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded-md text-sm font-medium ${
    isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800'
  }`;

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-700 bg-slate-800/60">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3">
          <span className="mr-4 text-lg font-bold text-amber-400">Top20 If 模拟器</span>
          <NavLink to="/" className={navCls} end>首页</NavLink>
          <NavLink to="/saves" className={navCls}>存档管理</NavLink>
          <NavLink to="/settings" className={navCls}>权重设置</NavLink>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/year/:year" element={<EventsPage />} />
          <Route path="/year/:year/event/:eventId" element={<ScenarioPage />} />
          <Route path="/year/:year/compare" element={<ComparePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/saves" element={<SavesPage />} />
        </Routes>
      </main>
    </div>
  );
}
