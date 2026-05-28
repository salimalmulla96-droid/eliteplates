import { useEffect, useMemo, useState } from 'react'
import { api, setErrorNotification, getSellerPlates } from './api'
import { CODE_OPTIONS, CITY_OPTIONS, NUMBER_FORMAT_OPTIONS, SEARCH_DEPTH_OPTIONS, SEARCH_MODE_OPTIONS, SORT_OPTIONS, ALERT_INTERVAL_OPTIONS } from './constants/options'
import Compare from './components/Compare'
import Dashboard from './components/Dashboard'
import Exports from './components/Exports'
import Favorites from './components/Favorites'
import ListingDetails from './components/ListingDetails'
import SavedSearches from './components/SavedSearches'
import SearchPage from './components/SearchPage'
import Sellers from './components/Sellers'
import Settings from './components/Settings'
import Alerts from './components/Alerts'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'

const defaultForm = {
  plate_number: '',
  search_mode: 'exact match',
  cities: [],
  city: '',
  code: '',
  price_min: '',
  price_max: '',
  contains: '',
  starts_with: '',
  ends_with: '',
  number_format: 'Any format',
  number_formats: [],
  search_depth: 'All pages',
  sort: 'Newest first',
  hide_duplicates: true,
  show_seller_details: true,
  price_position: 'Any price'
}

function App() {
  const [activePage, setActivePage] = useState('Search Plates')
  const [options, setOptions] = useState({
    cities: CITY_OPTIONS,
    number_formats: NUMBER_FORMAT_OPTIONS,
    search_depths: SEARCH_DEPTH_OPTIONS,
    sorts: SORT_OPTIONS,
    codes: CODE_OPTIONS,
    search_modes: SEARCH_MODE_OPTIONS,
    intervals: ALERT_INTERVAL_OPTIONS,
  })
  const [form, setForm] = useState(defaultForm)
  const [results, setResults] = useState([])
  const [summary, setSummary] = useState({})
  const [debug, setDebug] = useState({})
  const [history, setHistory] = useState([])
  const [favorites, setFavorites] = useState([])
  const [sellers, setSellers] = useState([])
  const [settings, setSettings] = useState({})
  const [selected, setSelected] = useState(null)
  const [selectedRows, setSelectedRows] = useState([])
  const [quickFilter, setQuickFilter] = useState('')
  const [status, setStatus] = useState('Ready')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(null)
  const [theme, setTheme] = useState('dark')
  const [errorMessage, setErrorMessage] = useState('')
  const [sellerView, setSellerView] = useState(null)

  useEffect(() => {
    setErrorNotification(setErrorMessage)
  }, [])

  useEffect(() => {
    Promise.all([api.options(), api.history(), api.favorites(), api.settings()])
      .then(([opt, hist, fav, set]) => {
        setOptions({
          cities: opt.cities || CITY_OPTIONS,
          number_formats: opt.number_formats || NUMBER_FORMAT_OPTIONS,
          search_depths: opt.search_depths || SEARCH_DEPTH_OPTIONS,
          sorts: opt.sorts || SORT_OPTIONS,
          codes: opt.codes || CODE_OPTIONS,
          search_modes: opt.search_modes || SEARCH_MODE_OPTIONS,
          intervals: opt.intervals || ALERT_INTERVAL_OPTIONS,
        })
        setHistory(hist.history)
        setFavorites(fav.favorites)
        setSettings(set.settings)
        setTheme(set.settings.theme || 'dark')
        setForm((current) => ({
          ...current,
          search_depth: set.settings.default_search_depth || 'All pages',
          show_seller_details: set.settings.show_seller_details !== false
        }))
      })
      .catch((error) => {
        setErrorMessage(error.isConnectionError ? error.message : 'Failed to load app data.')
      })
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
  }, [theme])

  useEffect(() => {
    if (!Object.keys(settings).length) return
    const updated = { ...settings, show_seller_details: form.show_seller_details !== false }
    setSettings(updated)
    api.saveSettings(updated).catch(() => {})
  }, [form.show_seller_details])

  const rowsForTable = sellerView?.results || results

  const visibleRows = useMemo(() => {
    let rows = [...rowsForTable]
    if (quickFilter.trim()) {
      const term = quickFilter.toLowerCase()
      rows = rows.filter((row) =>
        ['plate_number', 'code', 'city', 'price', 'seller_name', 'seller_username', 'phone_number']
          .some((key) => String(row[key] || '').toLowerCase().includes(term))
      )
    }
    return rows
  }, [rowsForTable, quickFilter])

  async function refreshSideData() {
    const [hist, fav, sell] = await Promise.all([api.history(), api.favorites(), api.sellers()])
    setHistory(hist.history)
    setFavorites(fav.favorites)
    setSellers(sell.sellers)
  }

  async function pollSearch(jobId) {
    while (true) {
      const job = await api.searchProgress(jobId)
      setProgress(job)
      setStatus(job.message || 'Searching...')
      if (job.status === 'done') break
      if (job.status === 'error') throw new Error(job.error || job.message || 'Search failed')
      await new Promise((resolve) => setTimeout(resolve, 900))
    }
    return api.searchResult(jobId)
  }

  async function runSearch(customForm = form) {
    setLoading(true)
    setErrorMessage('')
    setSellerView(null)
    setProgress({ message: 'Starting search...', progress_percent: null })
    setStatus('Searching...')
    try {
      const started = await api.startSearch(customForm)
      const data = await pollSearch(started.job_id)
      setResults(data.results)
      setSummary(data.summary)
      setDebug(data.debug)
      setSelected(data.results[0] || null)
      setStatus(`Done. Found ${data.results.length} results.`)
      setProgress({ message: `Done. Found ${data.results.length} results.`, progress_percent: 100, results_so_far: data.results.length })
      await refreshSideData()
    } catch (error) {
      setStatus('Search failed')
      setErrorMessage(error.isConnectionError ? error.message : error.message || 'Search failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function toggleFavorite(row) {
    try {
      const exists = favorites.some((item) => item.listing_link === row.listing_link)
      if (exists) {
        await api.deleteFavorite(row.listing_link)
      } else {
        await api.addFavorite(row)
      }
      await refreshSideData()
    } catch (error) {
      setErrorMessage(error.message || 'Failed to update favorite')
    }
  }

  async function runHistory(id) {
    const item = history.find((entry) => entry.id === id)
    if (item) {
      const restored = { ...defaultForm, ...item, cities: Array.isArray(item.cities) ? item.cities : item.city ? [item.city] : [] }
      setForm(restored)
      await runSearch(restored)
      setActivePage('Search Plates')
      return
    }
    setErrorMessage('Saved search was not found.')
  }

  async function viewSellerPlates(row) {
    if (!row) {
      setErrorMessage('Please select a listing first.')
      return
    }
    setLoading(true)
    setErrorMessage('')
    setStatus(`Loading seller plates for ${row.seller_name || row.seller_username || 'seller'}...`)
    try {
      const payload = {
        seller_username: row.seller_username || '',
        seller_name: row.seller_name || '',
        phone_number: row.phone_number || '',
        seller_profile_url: row.seller_link || row.seller_profile_url || '',
        current_results: results
      }
      const data = await getSellerPlates(payload)
      setSellerView(data)
      setSelected(data.results?.[0] || row)
      setActivePage('Search Plates')
      setStatus(`Loaded ${data.results?.length || 0} seller plates.`)
    } catch (error) {
      setErrorMessage(error.message || 'Failed to load seller plates')
      setStatus('Seller lookup failed')
    } finally {
      setLoading(false)
    }
  }

  async function exportCsv(rows, filename) {
    try {
      const data = await api.exportCsv(rows, filename)
      setStatus(`Exported CSV: ${data.path}`)
    } catch (error) {
      setErrorMessage(error.message || 'Failed to export CSV')
    }
  }

  async function exportExcel(rows, filename) {
    try {
      const data = await api.exportExcel(rows, filename)
      setStatus(`Exported Excel: ${data.path}`)
    } catch (error) {
      setErrorMessage(error.message || 'Failed to export Excel')
    }
  }

  const page = (() => {
    if (activePage === 'Dashboard') return <Dashboard summary={summary} history={history} favorites={favorites} sellers={sellers} results={results} />
    if (activePage === 'Saved Searches') return <SavedSearches history={history} runHistory={runHistory} deleteHistory={async (id) => { await api.deleteHistory(id); await refreshSideData() }} clearHistory={async () => { await api.clearHistory(); await refreshSideData() }} />
    if (activePage === 'Favorites') return <Favorites favorites={favorites} toggleFavorite={toggleFavorite} />
    if (activePage === 'Sellers') return <Sellers sellers={sellers} onViewSeller={viewSellerPlates} />
    if (activePage === 'Alerts') return <Alerts options={options} />
    if (activePage === 'Compare') return <Compare selectedRows={selectedRows} />
    if (activePage === 'Exports') return <Exports visibleRows={visibleRows} selectedRows={selectedRows} favorites={favorites} sellers={sellers} exportCsv={exportCsv} exportExcel={exportExcel} />
    if (activePage === 'Settings') return <Settings settings={settings} setSettings={setSettings} saveSettings={api.saveSettings} clearHistory={async () => { await api.clearHistory(); await refreshSideData() }} clearFavorites={async () => { await api.clearFavorites(); await refreshSideData() }} />
    return (
      <SearchPage
        form={form}
        setForm={setForm}
        options={options}
        onSearch={() => runSearch()}
        onClear={() => { setForm(defaultForm); setResults([]); setSelected(null); setSummary({}); setSellerView(null); setProgress(null) }}
        loading={loading}
        progress={progress}
        summary={sellerView ? { total_results: sellerView.results?.length || 0 } : summary}
        rows={visibleRows}
        selected={selected}
        setSelected={(row) => {
          setSelected(row)
          setSelectedRows((current) => current.some((item) => item.listing_link === row.listing_link) ? current : [...current, row])
        }}
        favorites={favorites}
        toggleFavorite={toggleFavorite}
        onViewSeller={viewSellerPlates}
        quickFilter={quickFilter}
        setQuickFilter={setQuickFilter}
        resetFilters={() => {
          setQuickFilter('')
          setSellerView(null)
          setForm((current) => ({
            ...current,
            cities: [],
            city: '',
            code: '',
            price_min: '',
            price_max: '',
            contains: '',
            starts_with: '',
            ends_with: '',
            number_format: 'Any format',
            hide_duplicates: true
          }))
        }}
        sellerView={sellerView}
        backToResults={() => { setSellerView(null); setSelected(results[0] || null) }}
        favorites={favorites}
        toggleFavorite={toggleFavorite}
        exportCsv={exportCsv}
        exportExcel={exportExcel}
      />
    )
  })()

  return (
    <div className="flex min-h-screen bg-ink text-slate-100">
      <Sidebar activePage={activePage} setActivePage={setActivePage} />
      <main className="flex min-w-0 flex-1 flex-col">
        <Topbar status={status} theme={theme} setTheme={setTheme} setActivePage={setActivePage} />
        {errorMessage && (
          <div className="flex items-center justify-between border-b border-red-700 bg-red-900/30 px-8 py-3">
            <p className="text-red-200">{errorMessage}</p>
            <button onClick={() => setErrorMessage('')} className="font-semibold text-red-300 hover:text-white">Close</button>
          </div>
        )}
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1 overflow-auto p-8">{page}</div>
          {activePage !== 'Alerts' && form.show_seller_details !== false && (
            <ListingDetails listing={selected} favorites={favorites} toggleFavorite={toggleFavorite} onViewSeller={viewSellerPlates} />
          )}
        </div>
      </main>
    </div>
  )
}

export default App
