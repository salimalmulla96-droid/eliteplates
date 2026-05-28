import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import SummaryCards from './SummaryCards'

export default function Dashboard({ summary, history, favorites, sellers, results }) {
  const chartData = results.slice(0, 12).map((row) => ({
    plate: row.plate_number,
    price: Number(String(row.price || '').replace(/[^0-9]/g, '')) || 0
  }))
  return (
    <div className="space-y-6">
      <SummaryCards summary={summary} />
      <div className="grid gap-6 xl:grid-cols-3">
        <section className="glass rounded-3xl p-6">
          <h3 className="mb-4 text-lg font-bold">Recent Searches</h3>
          <div className="space-y-3">
            {history.slice(0, 5).map((item) => (
              <div key={item.id} className="rounded-2xl bg-slate-900/60 p-3">
                <p className="font-semibold">{item.plate_number || item.number_format || 'Format search'}</p>
                <p className="text-sm text-slate-400">{item.datetime} • {item.result_count} results</p>
              </div>
            ))}
            {!history.length && <p className="text-slate-400">No saved searches yet.</p>}
          </div>
        </section>
        <section className="glass rounded-3xl p-6">
          <h3 className="mb-4 text-lg font-bold">Favorite Listings</h3>
          <div className="space-y-3">
            {favorites.slice(0, 5).map((item) => (
              <div key={item.listing_link} className="rounded-2xl bg-slate-900/60 p-3">
                <p className="font-semibold">{item.code} {item.plate_number}</p>
                <p className="text-sm text-slate-400">{item.city} • {item.price}</p>
              </div>
            ))}
            {!favorites.length && <p className="text-slate-400">No favorites yet. Star listings to save them here.</p>}
          </div>
        </section>
        <section className="glass rounded-3xl p-6">
          <h3 className="mb-4 text-lg font-bold">Top Sellers</h3>
          <div className="space-y-3">
            {sellers.slice(0, 5).map((seller) => (
              <div key={seller.seller_username} className="rounded-2xl bg-slate-900/60 p-3">
                <p className="font-semibold">{seller.seller_name}</p>
                <p className="text-sm text-slate-400">{seller.total_listings} listings • {seller.phone_number}</p>
              </div>
            ))}
            {!sellers.length && <p className="text-slate-400">Seller data appears after a search.</p>}
          </div>
        </section>
      </div>
      <section className="glass h-80 rounded-3xl p-6">
        <h3 className="mb-4 text-lg font-bold">Price Range</h3>
        <ResponsiveContainer width="100%" height="85%">
          <BarChart data={chartData}>
            <XAxis dataKey="plate" stroke="#94A3B8" />
            <YAxis stroke="#94A3B8" />
            <Tooltip contentStyle={{ background: '#111827', border: '1px solid #243044', color: '#fff' }} />
            <Bar dataKey="price" fill="#8B5CF6" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  )
}
