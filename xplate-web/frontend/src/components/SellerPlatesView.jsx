import { ArrowLeft, ExternalLink, Copy, Download, Star } from 'lucide-react'
import ResultsTable from './ResultsTable'
import SummaryCards from './SummaryCards'
import { api } from '../api'

export default function SellerPlatesView({ sellerView, backToResults, exportCsv, exportExcel, toggleFavorite, favorites }) {
  const seller = sellerView?.seller || {}
  const rows = sellerView?.results || []

  async function handleExport() {
    try {
      await api.exportCsv(rows, `seller_${seller.seller_username || 'plates'}`)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <section className="glass rounded-3xl p-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-black">Seller Plates</h2>
          <p className="mt-1 text-sm text-slate-400">Showing all plates found for {seller.seller_name || seller.seller_username || 'this seller'}</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-muted flex items-center gap-2" onClick={backToResults}><ArrowLeft size={16} /> Back to Results</button>
          {seller.seller_profile_url ? <a className="btn-muted flex items-center gap-2" href={seller.seller_profile_url} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Open Seller Profile</a> : null}
          <button className="btn-muted flex items-center gap-2" onClick={() => navigator.clipboard.writeText(seller.phone_number || '')}><Copy size={16} /> Copy Phone</button>
          <button className="btn-primary flex items-center gap-2" onClick={handleExport}><Download size={16} /> Export Seller Plates</button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl bg-panel p-3">Total plates: <strong>{seller.total_listings || 0}</strong></div>
        <div className="rounded-2xl bg-panel p-3">Cheapest: <strong>{seller.cheapest ? `AED ${Number(seller.cheapest).toLocaleString()}` : '?'}</strong></div>
        <div className="rounded-2xl bg-panel p-3">Most expensive: <strong>{seller.most_expensive ? `AED ${Number(seller.most_expensive).toLocaleString()}` : '?'}</strong></div>
        <div className="rounded-2xl bg-panel p-3">Cities: <strong>{(seller.cities || []).join(', ') || '?'}</strong></div>
      </div>

      <div className="mt-4">
        <ResultsTable rows={rows} selected={null} setSelected={() => {}} favorites={favorites} toggleFavorite={toggleFavorite} onViewSeller={null} quickFilter={''} setQuickFilter={() => {}} />
      </div>
      {!rows.length && (
        <div className="mt-6 text-center text-slate-400">No plates found for this seller.</div>
      )}
    </section>
  )
}
