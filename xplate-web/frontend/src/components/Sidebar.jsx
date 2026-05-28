import { BarChart3, Bookmark, Car, Download, GitCompare, Heart, History, Search, Settings, Users } from 'lucide-react'

const items = [
  ['Dashboard', BarChart3],
  ['Search Plates', Search],
  ['Saved Searches', History],
  ['Alerts', BarChart3],
  ['Favorites', Heart],
  ['Sellers', Users],
  ['Compare', GitCompare],
  ['Exports', Download],
  ['Settings', Settings]
]

export default function Sidebar({ activePage, setActivePage }) {
  return (
    <aside className="w-72 shrink-0 border-r border-line bg-[#080E1D] p-5">
      <div className="glass mb-6 rounded-3xl p-5">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent/20 text-accent">
            <Car />
          </div>
          <div>
            <h1 className="text-xl font-bold">Xplate Scout</h1>
            <p className="text-sm text-slate-400">UAE Plate Finder</p>
          </div>
        </div>
      </div>
      <nav className="space-y-2">
        {items.map(([label, Icon]) => {
          const active = label === activePage
          return (
            <button
              key={label}
              onClick={() => setActivePage(label)}
              className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm transition ${
                active ? 'bg-accent text-white shadow-lg shadow-violet-900/30' : 'text-slate-300 hover:bg-panel2 hover:text-white'
              }`}
            >
              <Icon size={18} />
              {label}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
