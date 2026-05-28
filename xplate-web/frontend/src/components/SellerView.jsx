import ResultsTable from './ResultsTable'

export default function SellerView({
  sellerData,
  onBack,
  onExport,
  sellersWatchlist,
  onToggleWatchlist
}) {
  const { seller, results } = sellerData
  const isWatched = sellersWatchlist.some(s => s.seller_username === seller.seller_username)

  const handleOpenProfile = () => {
    if (seller.seller_profile_url) {
      window.open(seller.seller_profile_url, '_blank')
    }
  }

  const handleCopyPhone = () => {
    if (seller.phone_number && seller.phone_number !== '?') {
      navigator.clipboard.writeText(seller.phone_number)
      alert(`Copied: ${seller.phone_number}`)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black">{seller.seller_name || 'Unknown Seller'}</h1>
          <p className="mt-2 text-slate-400">Viewing {results.length} plates from this seller</p>
        </div>
        <button
          onClick={onBack}
          className="btn-muted flex items-center gap-2 px-4 py-2"
        >
          ← Back to Results
        </button>
      </div>

      {/* Seller Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Seller Name</p>
          <p className="mt-2 text-lg font-bold text-slate-100">{seller.seller_name || 'Unknown'}</p>
        </div>
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Username</p>
          <p className="mt-2 text-lg font-bold text-purple-400">{seller.seller_username || '?'}</p>
        </div>
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Phone</p>
          <p className="mt-2 text-lg font-bold text-slate-100 break-all">{seller.phone_number || '?'}</p>
        </div>
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Total Plates</p>
          <p className="mt-2 text-lg font-bold text-emerald-400">{seller.total_listings}</p>
        </div>

        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Cheapest</p>
          <p className="mt-2 text-lg font-bold text-green-400">{seller.cheapest || 'N/A'}</p>
        </div>
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Most Expensive</p>
          <p className="mt-2 text-lg font-bold text-red-400">{seller.most_expensive || 'N/A'}</p>
        </div>
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Cities</p>
          <p className="mt-2 text-sm font-bold text-slate-100">{seller.cities.length > 0 ? seller.cities.join(', ') : 'N/A'}</p>
        </div>
        <div className="glass rounded-2xl p-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 font-semibold uppercase">Newest</p>
          <p className="mt-2 text-sm font-bold text-slate-100">{seller.newest_listing || 'N/A'}</p>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleOpenProfile}
          disabled={!seller.seller_profile_url}
          className="btn-primary flex items-center gap-2 px-4 py-2"
        >
          🔗 Open Seller Profile
        </button>
        <button
          onClick={handleCopyPhone}
          disabled={!seller.phone_number || seller.phone_number === '?'}
          className="btn-secondary flex items-center gap-2 px-4 py-2"
        >
          📋 Copy Phone
        </button>
        <button
          onClick={() => onToggleWatchlist(seller)}
          className={`${isWatched ? 'btn-danger' : 'btn-secondary'} flex items-center gap-2 px-4 py-2`}
        >
          {isWatched ? '⭐ Remove from Watchlist' : '☆ Add to Watchlist'}
        </button>
        <button
          onClick={() => onExport(results, `seller_${seller.seller_username}_plates`)}
          className="btn-secondary flex items-center gap-2 px-4 py-2"
        >
          📥 Export as CSV
        </button>
      </div>

      {/* Results Table */}
      <div>
        <h2 className="text-xl font-bold mb-4">📋 Seller's Plates ({results.length})</h2>
        {results.length > 0 ? (
          <div className="glass rounded-2xl overflow-hidden border border-slate-700/50">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 border-b border-slate-700/50 bg-slate-900/50">
                  <tr className="text-slate-300">
                    <th className="px-4 py-3 text-left font-semibold">City</th>
                    <th className="px-4 py-3 text-left font-semibold">Plate #</th>
                    <th className="px-4 py-3 text-left font-semibold">Code</th>
                    <th className="px-4 py-3 text-left font-semibold">Price</th>
                    <th className="px-4 py-3 text-left font-semibold">Date</th>
                    <th className="px-4 py-3 text-left font-semibold">Link</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((row, idx) => (
                    <tr
                      key={row.listing_link || idx}
                      className="border-b border-slate-700/30 hover:bg-slate-800/50 transition"
                    >
                      <td className="px-4 py-3 text-slate-200">{row.city || '?'}</td>
                      <td className="px-4 py-3 font-bold text-purple-400">{row.plate_number}</td>
                      <td className="px-4 py-3 text-slate-300">{row.code || '?'}</td>
                      <td className="px-4 py-3 text-emerald-400">{row.price || '?'}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{row.uploaded_date || '?'}</td>
                      <td className="px-4 py-3">
                        <a
                          href={row.listing_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 underline"
                        >
                          View
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="glass rounded-2xl p-8 text-center border border-slate-700/50">
            <p className="text-slate-400">No plates found for this seller in current results.</p>
          </div>
        )}
      </div>
    </div>
  )
}
