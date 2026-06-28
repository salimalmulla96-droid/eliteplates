import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'

function todayLocalIsoDate() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().split('T')[0]
}

export default function Exports({ visibleRows, selectedRows, favorites, sellers, exportCsv, exportExcel }) {
  const [selectedDate, setSelectedDate] = useState(todayLocalIsoDate)
  const [downloadState, setDownloadState] = useState({ loading: false, success: false, error: null })

  async function handleDownloadReport() {
    setDownloadState({ loading: true, success: false, error: null })
    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
      const isoDate = selectedDate // HTML date inputs always produce YYYY-MM-DD
      const url = `${API_BASE_URL}/reports/daily-excel?date=${isoDate}`
      console.log('Downloading daily report from:', url)

      let response
      try {
        response = await fetch(url)
      } catch (networkErr) {
        throw new Error('Backend server is not reachable. Make sure FastAPI is running on localhost:8000.')
      }

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('No daily report data found for this date.')
        }
        let msg = `Request failed: ${response.status}`
        try {
          const text = await response.text()
          const parsed = JSON.parse(text)
          msg = parsed.detail || parsed.message || msg
        } catch {
          // Keep the HTTP status message when the backend returns a file or plain text.
        }
        throw new Error(msg)
      }

      const blob = await response.blob()
      const blobUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `xplate_daily_report_${isoDate}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(blobUrl)

      setDownloadState({ loading: false, success: true, error: null })
    } catch (err) {
      console.error('Daily report download failed:', err)
      setDownloadState({ loading: false, success: false, error: err.message || 'Failed to download report' })
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
                setDownloadState({ loading: false, success: false, error: null })
              }}
            />
          </div>

          <button
            className="btn-primary w-full whitespace-nowrap sm:w-auto"
            onClick={handleDownloadReport}
            disabled={downloadState.loading || !selectedDate}
          >
            {downloadState.loading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            {downloadState.loading ? 'Generating...' : 'Download Daily Excel Report'}
          </button>
        </div>

        {downloadState.success && (
          <p className="mt-4 text-sm font-semibold text-emerald-400">Report successfully generated and downloaded.</p>
        )}
        {downloadState.error && (
          <p className="mt-4 text-sm font-semibold text-red-400">Error: {downloadState.error}</p>
        )}
      </section>
    </div>
  )
}
