import { Moon, Settings, Sun } from 'lucide-react'

export default function Topbar({ status, theme, setTheme, setActivePage }) {
  return (
    <header className="flex items-center justify-between border-b border-line bg-ink/80 px-8 py-5 backdrop-blur">
      <div>
        <p className="text-sm font-semibold text-accent">Welcome, Salim!</p>
        <h2 className="text-2xl font-bold">Premium Xplate dashboard</h2>
      </div>
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-line bg-panel px-4 py-2 text-sm text-slate-300">{status || 'Ready'}</span>
        <button className="btn-muted" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          {theme === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
        </button>
        <button className="btn-muted" onClick={() => setActivePage('Settings')}>
          <Settings size={16} />
        </button>
      </div>
    </header>
  )
}
