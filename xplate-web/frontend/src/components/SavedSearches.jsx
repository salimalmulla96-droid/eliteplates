export default function SavedSearches({ history, runHistory, deleteHistory, clearHistory }) {
  return (
    <section className="glass rounded-3xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black">Saved Searches</h1>
          <p className="mt-2 text-slate-400">Run, delete, or clear saved search history.</p>
        </div>
        <button className="btn-muted" onClick={clearHistory}>Clear all</button>
      </div>
      <div className="overflow-auto">
        <table className="w-full min-w-[1400px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500 border-b border-line">
            <tr>
              <th className="p-3">Plate/Format</th>
              <th>Contains</th>
              <th>Starts</th>
              <th>Ends</th>
              <th>Format</th>
              <th>City</th>
              <th>Price Range</th>
              <th>Search Depth</th>
              <th>Date/Time</th>
              <th>Results</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {history.map((item) => (
              <tr key={item.id} className="border-t border-line hover:bg-slate-900/40">
                <td className="p-3 font-medium text-purple-400">{item.plate_number || '(format search)'}</td>
                <td className="text-slate-300">{item.contains || '—'}</td>
                <td className="text-slate-300">{item.starts_with || '—'}</td>
                <td className="text-slate-300">{item.ends_with || '—'}</td>
                <td className="text-slate-300 text-xs">{item.number_format}</td>
                <td className="text-slate-300">{Array.isArray(item.cities) && item.cities.length ? item.cities.join(', ') : item.city || 'All'}</td>
                <td className="text-slate-300 text-xs">
                  {item.price_min || item.price_max ? `${item.price_min || '0'} - ${item.price_max || '∞'}` : 'Any'}
                </td>
                <td className="text-slate-300 text-xs">{item.search_depth}</td>
                <td className="text-slate-500 text-xs">{item.searched_at || item.datetime}</td>
                <td className="font-bold text-emerald-400">{item.result_count}</td>
                <td className="space-x-2 whitespace-nowrap">
                  <button className="text-xs px-2 py-1 rounded border border-purple-500 text-purple-300 hover:bg-purple-900/50" onClick={() => runHistory(item.id)}>▶️ Run</button>
                  <button className="text-xs px-2 py-1 rounded border border-red-500 text-red-300 hover:bg-red-900/50" onClick={() => deleteHistory(item.id)}>🗑️ Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!history.length && <p className="py-12 text-center text-slate-400">No saved searches yet.</p>}
      </div>
    </section>
  )
}
