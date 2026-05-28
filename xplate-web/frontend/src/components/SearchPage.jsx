import { ArrowLeft, Eraser, RotateCcw, Search } from 'lucide-react'
import CityMultiSelect from './CityMultiSelect'
import ResultsTable from './ResultsTable'
import SearchProgress from './SearchProgress'
import SummaryCards from './SummaryCards'
import SellerPlatesView from './SellerPlatesView'
import { CODE_OPTIONS, NUMBER_FORMAT_OPTIONS, SEARCH_MODE_OPTIONS, SEARCH_DEPTH_OPTIONS, SORT_OPTIONS } from '../constants/options'

export default function SearchPage({
  form,
  setForm,
  options,
  onSearch,
  onClear,
  loading,
  progress,
  summary,
  rows,
  selected,
  setSelected,
  favorites,
  toggleFavorite,
  onViewSeller,
  quickFilter,
  setQuickFilter,
  resetFilters,
  sellerView,
  backToResults,
  exportCsv,
  exportExcel
}) {
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black">Search Plates</h1>
          <p className="mt-2 text-slate-400">Search UAE license plates by number, seller, price, city, and number format.</p>
        </div>
        {sellerView && (
          <button className="btn-muted flex items-center gap-2" onClick={backToResults}>
            <ArrowLeft size={16} /> Back to Results
          </button>
        )}
      </div>

      <section className="glass rounded-3xl border border-slate-700/50 p-6">
        <div className="grid gap-4 xl:grid-cols-4">
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Plate number</label>
            <input className="input" placeholder="Enter plate number, or leave empty for format search" value={form.plate_number} onChange={(event) => update('plate_number', event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Search mode</label>
            <select className="input" value={form.search_mode} onChange={(event) => update('search_mode', event.target.value)}>
              {SEARCH_MODE_OPTIONS.map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">City</label>
            <CityMultiSelect value={form.cities || []} onChange={(cities) => setForm((current) => ({ ...current, cities, city: cities[0] || '' }))} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Code</label>
            <select className="input" value={form.code || ''} onChange={(event) => update('code', event.target.value === 'Any code' ? '' : event.target.value)}>
              {CODE_OPTIONS.map((item) => <option key={item} value={item === 'Any code' ? '' : item}>{item}</option>)}
            </select>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-4">
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Contains</label>
            <input className="input" placeholder="Contains digits, example: 77" value={form.contains || ''} onChange={(event) => update('contains', event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Starts With</label>
            <input className="input" placeholder="Starts with, example: 12" value={form.starts_with || ''} onChange={(event) => update('starts_with', event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Ends With</label>
            <input className="input" placeholder="Ends with, example: 00" value={form.ends_with || ''} onChange={(event) => update('ends_with', event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Number Format</label>
            <select className="input" value={form.number_format} onChange={(event) => update('number_format', event.target.value)}>
              {NUMBER_FORMAT_OPTIONS.map((item) => <option key={item}>{item}</option>)}
            </select>
            <p className="mt-1 text-[11px] text-slate-500">Searches Xplate by format, then validates locally.</p>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-4">
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Min price</label>
            <input className="input" placeholder="Min price" value={form.price_min} onChange={(event) => update('price_min', event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Max price</label>
            <input className="input" placeholder="Max price" value={form.price_max} onChange={(event) => update('price_max', event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Search depth</label>
            <select className="input" value={form.search_depth} onChange={(event) => update('search_depth', event.target.value)}>
              {SEARCH_DEPTH_OPTIONS.map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">Sort</label>
            <select className="input" value={form.sort} onChange={(event) => update('sort', event.target.value)}>
              {SORT_OPTIONS.map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/50 px-3 py-2.5 text-sm text-slate-300">
            <input type="checkbox" checked={form.hide_duplicates} onChange={(event) => update('hide_duplicates', event.target.checked)} />
            <span>Hide duplicates</span>
          </label>
          <label className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/50 px-3 py-2.5 text-sm text-slate-300">
            <input type="checkbox" checked={form.show_seller_details !== false} onChange={(event) => update('show_seller_details', event.target.checked)} />
            <span>Show seller details</span>
          </label>
          <div className="flex-1" />
          <button className="btn-primary flex min-w-44 items-center justify-center gap-2" disabled={loading} onClick={onSearch}>
            <Search size={16} /> {loading ? 'Searching...' : 'Search'}
          </button>
          <button className="btn-muted flex items-center gap-2" onClick={onClear}><Eraser size={16} /> Clear</button>
          <button className="btn-muted flex items-center gap-2" onClick={resetFilters}><RotateCcw size={16} /> Reset Filters</button>
        </div>
      </section>

      <SearchProgress loading={loading} progress={progress} />

      {sellerView && (
        <SellerPlatesView sellerView={sellerView} backToResults={backToResults} exportCsv={exportCsv} exportExcel={exportExcel} toggleFavorite={toggleFavorite} favorites={favorites} />
      )}

      <SummaryCards summary={summary} />

      <ResultsTable
        rows={rows}
        selected={selected}
        setSelected={setSelected}
        favorites={favorites}
        toggleFavorite={toggleFavorite}
        onViewSeller={onViewSeller}
        quickFilter={quickFilter}
        setQuickFilter={setQuickFilter}
      />
    </div>
  )
}
