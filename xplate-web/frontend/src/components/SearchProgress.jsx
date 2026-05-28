import { Loader2 } from 'lucide-react'

export default function SearchProgress({ loading, progress }) {
  if (!loading && !progress?.message) return null
  const percent = typeof progress?.progress_percent === 'number' ? Math.max(0, Math.min(progress.progress_percent, 100)) : null
  return (
    <section className="glass rounded-3xl p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-bold text-slate-100">
            {loading && <Loader2 size={16} className="animate-spin text-purple-300" />}
            {progress?.message || 'Searching...'}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {progress?.current_city ? `City: ${progress.current_city}` : 'Preparing search'}
            {progress?.current_page ? ` · Page ${progress.current_page}` : ''}
            {progress?.results_so_far ? ` · ${progress.results_so_far} loaded` : ''}
            {progress?.estimated_seconds_remaining ? ` · about ${progress.estimated_seconds_remaining}s remaining` : ''}
          </p>
        </div>
        <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-3 py-1 text-xs font-semibold text-purple-200">
          {percent === null ? 'Live' : `${percent}%`}
        </span>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r from-blue-400 via-purple-400 to-fuchsia-400 transition-all ${percent === null ? 'w-1/2 animate-pulse' : ''}`}
          style={percent === null ? undefined : { width: `${percent}%` }}
        />
      </div>
    </section>
  )
}
