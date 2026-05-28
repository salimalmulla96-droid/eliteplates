export default function Exports({ visibleRows, selectedRows, favorites, sellers, exportCsv, exportExcel }) {
  return (
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
  )
}
