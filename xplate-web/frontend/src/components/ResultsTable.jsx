import { Copy, ExternalLink, Star } from 'lucide-react'

const columns = [
  ['Favorite', 'favorite'],
  ['Plate Number', 'plate_number'],
  ['Code', 'code'],
  ['City', 'city'],
  ['Price', 'price'],
  ['Seller Name', 'seller_name'],
  ['Username', 'seller_username'],
  ['Phone', 'phone_number'],
  ['Uploaded Date', 'uploaded_date'],
  ['Uploaded Time', 'uploaded_time'],
  ['Age', 'age_text'],
  ['Deal Rank', 'deal_rank'],
  ['Listing URL', 'listing_link']
]

export default function ResultsTable({
  rows,
  selected,
  setSelected,
  favorites,
  toggleFavorite,
  onViewSeller,
  quickFilter,
  setQuickFilter
}) {
  const favoriteLinks = new Set(favorites.map((item) => item.listing_link))
  return (
    <section className="glass flex min-h-[520px] flex-col rounded-3xl">
      <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
        <input
          className="input max-w-md"
          placeholder="Search within results..."
          value={quickFilter}
          onChange={(event) => setQuickFilter(event.target.value)}
        />
        <span className="text-sm text-slate-400">{rows.length} visible rows</span>
      </div>
      <div className="overflow-auto">
        <table className="min-w-[1500px] w-full text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#151B2D] text-xs uppercase text-slate-400">
            <tr>
              {columns.map(([label]) => <th key={label} className="px-4 py-3">{label}</th>)}
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const isSelected = selected?.listing_link === row.listing_link
              const favorite = favoriteLinks.has(row.listing_link)
              const tag =
                row.deal_rank === 'Cheapest' ? 'bg-emerald-950/60' :
                index === 0 ? 'bg-blue-950/40' : index % 2 ? 'bg-slate-950/20' : 'bg-slate-900/30'
              return (
                <tr
                  key={row.listing_link || index}
                  onClick={() => setSelected(row)}
                  onDoubleClick={() => window.open(row.listing_link, '_blank')}
                  className={`${tag} cursor-pointer border-b border-line/50 hover:bg-violet-950/30 ${isSelected ? 'outline outline-2 outline-accent bg-accent/5' : ''}`}
                >
                  <td className="px-4 py-3">
                    <button onClick={(event) => { event.stopPropagation(); toggleFavorite(row) }} className={favorite ? 'text-yellow-400' : 'text-slate-500'}>
                      <Star size={16} fill={favorite ? 'currentColor' : 'none'} />
                    </button>
                  </td>
                  <td className="px-4 py-3 font-bold">{row.plate_number}</td>
                  <td className="px-4 py-3">{row.code}</td>
                  <td className="px-4 py-3">{row.city}</td>
                  <td className="px-4 py-3">{row.price}</td>
                  <td className="px-4 py-3 text-cyan hover:underline cursor-pointer" onClick={(event) => { event.stopPropagation(); setSelected(row); onViewSeller?.(row) }}>{row.seller_name}</td>
                  <td className="px-4 py-3 text-cyan hover:underline cursor-pointer" onClick={(event) => { event.stopPropagation(); setSelected(row); onViewSeller?.(row) }}>{row.seller_username}</td>
                  <td className="px-4 py-3">{row.phone_number}</td>
                  <td className="px-4 py-3">{row.uploaded_date}</td>
                  <td className="px-4 py-3">{row.uploaded_time}</td>
                  <td className="px-4 py-3">{row.age_text}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs ${row.deal_rank === 'Cheapest' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-300'}`}>{row.deal_rank}</span>
                  </td>
                  <td className="max-w-xs break-words px-4 py-3 text-slate-400">{row.listing_link}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button className="text-slate-300 hover:text-white" onClick={(event) => { event.stopPropagation(); window.open(row.listing_link, '_blank') }}><ExternalLink size={16} /></button>
                      <button className="text-slate-300 hover:text-white" onClick={(event) => { event.stopPropagation(); navigator.clipboard.writeText(row.phone_number || '') }}><Copy size={16} /></button>
                      {onViewSeller && <button className="text-purple-400 hover:text-purple-300 text-xs px-2 py-1 rounded border border-purple-500/50" onClick={(event) => { event.stopPropagation(); onViewSeller(row) }}>View Seller</button>}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!rows.length && (
          <div className="grid h-72 place-items-center text-center">
            <div>
              <h3 className="text-xl font-bold">No matching plates found.</h3>
              <p className="mt-2 text-slate-400">Try changing the city, price, or number format.</p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
