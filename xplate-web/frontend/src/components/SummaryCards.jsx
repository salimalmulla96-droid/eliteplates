import { Banknote, Car, Clock, Phone, Tags, TrendingDown, TrendingUp, Users } from 'lucide-react'

const cards = [
  ['Total Results', 'total_results', Car],
  ['Cheapest Plate', 'cheapest_price', TrendingDown],
  ['Most Expensive', 'most_expensive_price', TrendingUp],
  ['Average Price', 'average_price', Banknote],
  ['Cities Found', 'cities_found', Tags],
  ['Sellers Found', 'sellers_found', Users],
  ['With Phone', 'with_phone', Phone],
  ['Newest Listing', 'newest_listing', Clock]
]

function formatMoney(value) {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return String(value)
  return `AED ${Math.round(num).toLocaleString()}`
}

function formatDate(value) {
  if (!value) return '-'
  try {
    // Accept 'YYYY-MM-DD HH:MM:SS' or similar
    const normalized = String(value).replace(' ', 'T')
    const dt = new Date(normalized)
    if (isNaN(dt.getTime())) return String(value)
    const yyyy = dt.getFullYear()
    const mm = String(dt.getMonth() + 1).padStart(2, '0')
    const dd = String(dt.getDate()).padStart(2, '0')
    const hh = String(dt.getHours()).padStart(2, '0')
    const min = String(dt.getMinutes()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd} ${hh}:${min}`
  } catch (e) {
    return String(value)
  }
}

function fmtByKey(key, value) {
  if (value === null || value === undefined || value === '') return '-'
  if (['cheapest_price', 'most_expensive_price', 'average_price'].includes(key)) return formatMoney(value)
  if (key === 'newest_listing') return formatDate(value)
  return String(value)
}

export default function SummaryCards({ summary = {} }) {
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
      {cards.map(([label, key, Icon]) => (
        <div key={key} className="glass rounded-3xl p-4 min-w-[160px]">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
            <Icon size={16} className="text-accent" />
          </div>
          <div title={String(summary[key] ?? '')} className="text-xl font-bold leading-tight break-words whitespace-normal">
            {fmtByKey(key, summary[key])}
          </div>
        </div>
      ))}
    </div>
  )
}
