export default function Sellers({ sellers = [], sellersWatchlist = [], setSellerFilter, onViewSeller, onToggleWatchlist }) {
  const watchedUsernames = new Set(sellersWatchlist.map(s => s.seller_username))

  return (
    <section className="glass rounded-3xl p-6">
      <h1 className="text-3xl font-black">Sellers</h1>
      <p className="mt-2 text-slate-400">Seller summary from the current or latest search results.</p>
      
      {sellersWatchlist.length > 0 && (
        <div className="mt-6 mb-6">
          <h2 className="text-lg font-bold mb-3">⭐ Watched Sellers ({sellersWatchlist.length})</h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {sellersWatchlist.map((seller) => (
              <div key={seller.seller_username} className="rounded-xl border border-purple-500/50 bg-purple-900/20 p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-bold text-slate-100">{seller.seller_name}</p>
                    <p className="text-sm text-purple-400">@{seller.seller_username}</p>
                    <p className="mt-2 text-sm text-slate-300">📞 {seller.phone_number}</p>
                    <p className="text-xs text-slate-500 mt-1">Added: {seller.date_added}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {seller.seller_profile_url && (
                    <button
                      onClick={() => window.open(seller.seller_profile_url, '_blank')}
                      className="text-xs px-2 py-1 rounded border border-purple-500 text-purple-300 hover:bg-purple-900/50"
                    >
                      🔗 Profile
                    </button>
                  )}
                  <button
                    onClick={() => onToggleWatchlist(seller)}
                    className="text-xs px-2 py-1 rounded border border-red-500 text-red-300 hover:bg-red-900/50"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 overflow-auto">
        <table className="w-full min-w-[1200px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500 border-b border-line">
            <tr>
              <th className="p-3">Seller</th>
              <th>Username</th>
              <th>Phone</th>
              <th>Total</th>
              <th>Cheapest</th>
              <th>Most Expensive</th>
              <th>Cities</th>
              <th>Last Upload</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sellers.map((seller) => {
              const isWatched = watchedUsernames.has(seller.seller_username)
              return (
                <tr
                  key={seller.seller_username}
                  className={`border-t border-line hover:bg-slate-900/40 ${isWatched ? 'bg-purple-900/20' : ''}`}
                >
                  <td className="p-3 font-medium">{seller.seller_name}</td>
                  <td className="text-purple-400">@{seller.seller_username}</td>
                  <td className="text-slate-300">{seller.phone_number}</td>
                  <td className="font-bold text-emerald-400">{seller.total_listings}</td>
                  <td className="text-green-400">{seller.cheapest_listing}</td>
                  <td className="text-red-400">{seller.most_expensive_listing}</td>
                  <td className="text-sm">{seller.cities_used}</td>
                  <td className="text-xs text-slate-500">{seller.last_upload_date}</td>
                  <td className="space-x-2 whitespace-nowrap">
                    {onViewSeller && (
                      <button
                        className="text-xs px-2 py-1 rounded border border-purple-500 text-purple-300 hover:bg-purple-900/50"
                        onClick={() => onViewSeller(seller)}
                      >
                        👁️ View
                      </button>
                    )}
                    <button
                      className="text-xs px-2 py-1 rounded border border-slate-500 text-slate-300 hover:bg-slate-900/50"
                      onClick={() => navigator.clipboard.writeText(seller.phone_number || '')}
                    >
                      📋 Copy
                    </button>
                    <button
                      className="text-xs px-2 py-1 rounded border border-slate-500 text-slate-300 hover:bg-slate-900/50"
                      onClick={() => window.open(seller.seller_link, '_blank')}
                    >
                      🔗 Link
                    </button>
                    {onToggleWatchlist && (
                      <button
                        className={`text-xs px-2 py-1 rounded border ${isWatched ? 'border-yellow-500 text-yellow-400 hover:bg-yellow-900/50' : 'border-slate-500 text-slate-300 hover:bg-slate-900/50'}`}
                        onClick={() => onToggleWatchlist(seller)}
                      >
                        {isWatched ? '⭐' : '☆'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!sellers.length && <p className="py-12 text-center text-slate-400">Seller data appears after a search.</p>}
      </div>
    </section>
  )
}
