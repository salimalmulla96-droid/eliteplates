import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export function todayUaeIsoDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Dubai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

export default function Exports({ visibleRows, selectedRows, favorites, sellers, exportCsv, exportExcel }) {
  const [selectedDate, setSelectedDate] = useState(todayUaeIsoDate)
  const [downloadState, setDownloadState] = useState({ loading: false, success: false, error: null, message: '' })

  async function handleDownloadReport() {
    const uaeToday = todayUaeIsoDate()
    const isoDate = selectedDate || uaeToday
    if (!selectedDate) setSelectedDate(isoDate)
    setDownloadState({
      loading: true,
      success: false,
      error: null,
      message: isoDate === uaeToday ? 'Downloading today’s Excel report...' : `Downloading Excel report for ${isoDate}...`,
    })
    try {
      const url = `${API_BASE_URL}/reports/daily-excel?date=${isoDate}`
      console.log('Downloading daily Excel report from:', url)

      let response
      try {
        response = await fetch(url)
      } catch {
        throw new Error('Backend server is not reachable.')
      }

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error(isoDate === uaeToday ? 'No plates found for today.' : `No plates found for ${isoDate}.`)
        }
        try {
          const text = await response.text()
          console.error('Daily report backend error:', text)
        } catch {
          // The friendly message below is sufficient when no response body is available.
        }
        throw new Error('Report download failed.')
      }

      const blob = await response.blob()
      const blobUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `XPLATE REPORT ${isoDate}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(blobUrl)

      setDownloadState({
        loading: false,
        success: true,
        error: null,
        message: 'Daily Excel report downloaded successfully.',
      })
    } catch (err) {
      console.error('Daily report download failed:', err)
      const errorMessage = [
        'Backend server is not reachable.',
        'No plates found for today.',
        `No plates found for ${isoDate}.`,
        'Report download failed.',
      ].includes(err?.message) ? err.message : 'Report download failed.'
      setDownloadState({ loading: false, success: false, error: errorMessage, message: '' })
    }
  }

  return (
    <div className="space-y-6">
      <section className="glass max-w-3xl rounded-3xl p-6">
        <h1 className="text-3xl font-black">Exports</h1>
        <p className="mt-2 text-slate-400">Export visible rows, selected listings, favorites, or seller summaries.</p>
        <div className="mt-6 grid gap-3">
          <button className="btn-primary" onClick={() => exportCsv(visibleRows, 'visible_results')}>Export current visible results to CSV</button>
          <button className="btn-primary" onClick={() => exportExcel(visibleRows, 'visible_results')}>Export current visible results to Excel</button>
          <button className="btn-muted" onClick={() => exportExcel(selectedRows, 'selected_rows')}>Export selected rows only</button>
          <button className="btn-muted" onClick={() => exportExcel(favorites, 'favorites')}>Export favorites</button>
          <button className="btn-muted" onClick={() => exportExcel(sellers, 'seller_summary')}>Export seller summary</button>
        </div>
      </section>

      <section className="glass max-w-3xl rounded-3xl p-6">
        <h2 className="text-2xl font-black">Daily Plate Reports</h2>
        <p className="mt-2 text-slate-400">Download a compiled daily Excel report containing all plates listed on a specific date, grouped by emirate.</p>

        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="w-full flex-1">
            <label className="mb-2 block text-sm font-semibold text-slate-300">Report Date</label>
            <input
              type="date"
              className="input rounded-xl border-slate-700/60 bg-[#0F172A] text-white"
              value={selectedDate}
              onChange={(event) => {
                setSelectedDate(event.target.value)
                setDownloadState({ loading: false, success: false, error: null, message: '' })
              }}
            />
          </div>

          <button
            className="btn-primary w-full whitespace-nowrap sm:w-auto"
            onClick={handleDownloadReport}
            disabled={downloadState.loading}
          >
            {downloadState.loading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            {downloadState.loading ? 'Downloading...' : 'Download Daily Excel'}
          </button>
        </div>

        {downloadState.message && (
          <p className={`mt-4 text-sm font-semibold ${downloadState.success ? 'text-emerald-400' : 'text-sky-300'}`}>
            {downloadState.message}
          </p>
        )}
        {downloadState.error && (
          <p className="mt-4 text-sm font-semibold text-red-400">Error: {downloadState.error}</p>
        )}
      </section>
    </div>
  )
}
