import { Check, ChevronDown, MapPin, X } from 'lucide-react'
import { useMemo, useState } from 'react'

const cities = [
  ['Dubai', 'Dubai'],
  ['Abu Dhabi', 'Abu Dhabi'],
  ['Sharjah', 'Sharjah'],
  ['Ajman', 'Ajman'],
  ['Ras Al Khaimah', 'Ras Al Khaimah'],
  ['Umm Al Quwain', 'Umm Al Quwain'],
  ['Fujairah', 'Fujairah']
]

const cityLookup = new Map(
  cities.flatMap(([label, value]) => [
    [label.toLowerCase(), value],
    [value.toLowerCase(), value],
    [value.toLowerCase().replaceAll(' ', '-'), value],
  ])
)

function normalizeCity(value) {
  const text = String(value || '').trim()
  if (!text || ['all', 'all cities'].includes(text.toLowerCase())) return ''
  return cityLookup.get(text.toLowerCase()) || text
}

export default function CityMultiSelect({ value = [], onChange }) {
  const [open, setOpen] = useState(false)
  const selected = Array.from(new Set((Array.isArray(value) ? value : [value]).map(normalizeCity).filter(Boolean)))
  const labels = useMemo(() => {
    if (!selected.length) return 'All cities'
    return selected.map((city) => cities.find(([, val]) => val === city)?.[0] || city).join(', ')
  }, [selected])

  function toggle(city) {
    const normalizedCity = normalizeCity(city)
    if (selected.includes(normalizedCity)) {
      onChange(selected.filter((item) => item !== normalizedCity))
      return
    }
    onChange([...selected, normalizedCity])
  }

  return (
    <div className="relative">
      <button type="button" className="input flex items-center justify-between gap-2 text-left" onClick={() => setOpen((current) => !current)}>
        <span className="flex min-w-0 items-center gap-2">
          <MapPin size={15} className="text-purple-300" />
          <span className="truncate">{labels}</span>
        </span>
        <ChevronDown size={16} className="text-slate-400" />
      </button>
      {open && (
        <div className="absolute z-30 mt-2 w-full overflow-hidden rounded-2xl border border-line bg-[#0B1020] p-2 shadow-2xl">
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
            onClick={() => onChange([])}
          >
            <span>All cities</span>
            {!selected.length && <Check size={15} className="text-emerald-300" />}
          </button>
          {cities.map(([label, city]) => (
            <button
              type="button"
              key={city}
              className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
              onClick={() => toggle(city)}
            >
              <span>{label}</span>
              {selected.includes(city) && <Check size={15} className="text-emerald-300" />}
            </button>
          ))}
          {!!selected.length && (
            <button type="button" className="mt-1 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-800 px-3 py-2 text-xs text-slate-300 hover:bg-slate-700" onClick={() => onChange([])}>
              <X size={13} /> Clear cities
            </button>
          )}
        </div>
      )}
    </div>
  )
}
