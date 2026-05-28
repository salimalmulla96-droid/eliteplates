export default function Favorites({ favorites, toggleFavorite }) {
  return (
    <section className="glass rounded-3xl p-6">
      <h1 className="text-3xl font-black">Favorites</h1>
      <p className="mt-2 text-slate-400">Favorite listings remain after refresh and reopening the site.</p>
      <div className="mt-6 overflow-auto">
        <table className="w-full min-w-[1100px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr><th className="p-3">Plate</th><th>Code</th><th>City</th><th>Price</th><th>Seller</th><th>Username</th><th>Phone</th><th>Date</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {favorites.map((item) => (
              <tr key={item.listing_link} className="border-t border-line hover:bg-slate-900/40">
                <td className="p-3 font-bold">{item.plate_number}</td><td>{item.code}</td><td>{item.city}</td><td>{item.price}</td><td>{item.seller_name}</td><td>{item.seller_username}</td><td>{item.phone_number}</td><td>{item.uploaded_date}</td>
                <td className="space-x-2">
                  <button className="chip" onClick={() => window.open(item.listing_link, '_blank')}>Open listing</button>
                  <button className="chip" onClick={() => window.open(item.seller_link, '_blank')}>Seller</button>
                  <button className="chip" onClick={() => navigator.clipboard.writeText(item.phone_number || '')}>Copy phone</button>
                  <button className="chip" onClick={() => toggleFavorite(item)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!favorites.length && <p className="py-12 text-center text-slate-400">No favorites yet. Star listings to save them here.</p>}
      </div>
    </section>
  )
}
