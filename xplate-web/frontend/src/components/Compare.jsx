function priceNumber(row) {
  return Number(String(row.price || '').replace(/[^0-9]/g, '')) || 0
}

export default function Compare({ selectedRows }) {
  const cheapest = selectedRows.length ? selectedRows.reduce((a, b) => priceNumber(a) <= priceNumber(b) ? a : b) : null
  const newest = selectedRows.length ? [...selectedRows].sort((a, b) => `${b.uploaded_date} ${b.uploaded_time}`.localeCompare(`${a.uploaded_date} ${a.uploaded_time}`))[0] : null
  const prices = selectedRows.map(priceNumber).filter(Boolean)
  const sameSeller = new Set(selectedRows.map((row) => row.seller_username)).size <= 1
  const sameCity = new Set(selectedRows.map((row) => row.city)).size <= 1
  return (
    <section className="space-y-6">
      <div className="glass rounded-3xl p-6">
        <h1 className="text-3xl font-black">Compare</h1>
        <p className="mt-2 text-slate-400">Select rows in Search Plates, then open this page.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-5">
        <div className="glass rounded-3xl p-4">Cheapest: <b>{cheapest ? `${cheapest.code} ${cheapest.plate_number}` : '-'}</b></div>
        <div className="glass rounded-3xl p-4">Newest: <b>{newest ? `${newest.code} ${newest.plate_number}` : '-'}</b></div>
        <div className="glass rounded-3xl p-4">Price diff: <b>{prices.length ? `AED ${(Math.max(...prices) - Math.min(...prices)).toLocaleString()}` : '-'}</b></div>
        <div className="glass rounded-3xl p-4">{sameSeller ? 'Same seller' : 'Different sellers'}</div>
        <div className="glass rounded-3xl p-4">{sameCity ? 'Same city' : 'Different cities'}</div>
      </div>
      <div className="glass overflow-auto rounded-3xl p-6">
        <table className="w-full min-w-[1000px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500"><tr><th className="p-3">Plate</th><th>Price</th><th>City</th><th>Code</th><th>Seller</th><th>Phone</th><th>Date</th><th>Deal</th><th>URL</th></tr></thead>
          <tbody>{selectedRows.map((row) => <tr key={row.listing_link} className="border-t border-line"><td className="p-3">{row.plate_number}</td><td>{row.price}</td><td>{row.city}</td><td>{row.code}</td><td>{row.seller_name}</td><td>{row.phone_number}</td><td>{row.uploaded_date}</td><td>{row.deal_rank}</td><td className="truncate">{row.listing_link}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  )
}
