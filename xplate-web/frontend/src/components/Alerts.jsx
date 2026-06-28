import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronDown,
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Gauge,
  Image,
  MessageSquare,
  MoreHorizontal,
  Play,
  Radio,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Trash2,
  XCircle,
} from 'lucide-react'
import {
  api,
  getAlerts,
  createAlert,
  updateAlert,
  deleteAlert,
  toggleAlert,
  disableOtherAlerts,
  testTelegram,
  testTelegramChannel,
  runAlertNow,
  debugAlertScan,
  forceSendTestListing,
  resetAlertBaseline,
  sendDailyRuleReport,
  downloadDailyRuleReport,
  getAlertLogs,
  clearAlertLogs,
  stopAllAlerts,
} from '../api'
import CityMultiSelect from './CityMultiSelect'
import { CODE_OPTIONS, NUMBER_FORMAT_OPTIONS, SEARCH_MODE_OPTIONS, ALERT_INTERVAL_OPTIONS } from '../constants/options'

const DEFAULT_ALERT = {
  name: '',
  plate_number: '',
  search_mode: 'Send all new plates',
  cities: [],
  city: '',
  code: '',
  price_min: '',
  price_max: '',
  contains: '',
  starts_with: '',
  ends_with: '',
  number_format: 'Any format',
  number_formats: [],
  check_interval_minutes: 10,
  check_interval_seconds: 20,
  monitoring_interval_seconds: 20,
  monitoring_interval_mode: 'preset',
  custom_interval_value: '',
  custom_interval_unit: 'seconds',
  telegram_bot_token: '',
  telegram_chat_id: '',
  telegram_message_title: 'New Plate Alert',
  telegram_compact_mode: false,
  telegram_emojis: true,
  telegram_include_seller_details: true,
  telegram_include_detected_time: true,
  telegram_include_match_reason: true,
  send_all_new_plates: true,
  immediate_alerts_mode: true,
  fast_alert_mode: true,
  enrich_listing_details: false,
  include_sold_listings: false,
  include_featured_listings: false,
  max_listings_per_scan: 1000,
  max_pages_per_scan: 20,
  fresh_listing_window_minutes: 15,
  alert_once_per_listing: true,
  alert_only_price_below: true,
  alert_only_new: true,
  enabled: true,
  baseline_created: false,
  max_seen_listing_id: 0,
  seen_listing_ids: [],
  seen_listing_urls: [],
  seen_listing_keys: [],
  sent_listing_keys: [],
  baseline_created_at: '',
  last_scan_at: '',
}

const DEFAULT_INSTAGRAM_SETTINGS = {
  enabled: false,
  instagram_provider: 'Apify',
  apify_api_token: '',
  apify_actor_id: 'apify/instagram-post-scraper',
  provider_connected: false,
  last_provider_error: '',
  accounts: [
    { username: 'rak.number', enabled: true },
    { username: 'PLATESELITE', enabled: true },
  ],
  check_interval_minutes: 10,
  send_all_new_posts: true,
  extract_plate_numbers: false,
  send_instagram_image_to_telegram: true,
  extract_plate_details_from_images: false,
  include_caption: false,
  include_post_image: true,
  baseline_completed: false,
  instagram_activated_at: '',
  instagram_baseline_created_at: '',
  seen_instagram_posts: {},
  last_instagram_scan_at: '',
  last_baseline_reset_at: '',
  last_checked_at: '',
}

const tabs = ['Alert Rules', 'Telegram Setup', 'Instagram Setup', 'Monitoring & Logs']
const logFilters = ['All', 'Success', 'Warning', 'Error', 'Sent', 'Skipped', 'Match', 'No match']
const intervalPresets = [
  { seconds: 20, label: '20 sec' },
  { seconds: 30, label: '30 sec' },
  { seconds: 60, label: '1 min' },
  { seconds: 300, label: '5 min' },
  { seconds: 1200, label: '20 min' },
]

const defaultDailyReportDate = new Date(Date.now() + (4 * 60 * 60 * 1000) - (24 * 60 * 60 * 1000))
  .toISOString()
  .slice(0, 10)

function friendlyDailyReportError(error) {
  const message = String(error?.message || '')
  const lowered = message.toLowerCase()
  if (error?.isConnectionError || lowered.includes('failed to fetch') || lowered.includes('backend connection')) {
    return 'Backend server is not reachable.'
  }
  if (lowered.includes('telegram is not configured') || lowered.includes('telegram bot token') || lowered.includes('telegram channel')) {
    return 'Telegram is not configured.'
  }
  if (lowered.includes('no plates found') || lowered.includes('no data found')) {
    return 'No plates found for this rule on this date.'
  }
  if (lowered.includes('disabled rules')) return 'Enable this rule before generating its daily report.'
  return message || 'Report generation failed.'
}
const presetIntervalSeconds = intervalPresets.map((preset) => preset.seconds)

const CITY_OPTIONS = [
  'Dubai',
  'Abu Dhabi',
  'Sharjah',
  'Ajman',
  'Ras Al Khaimah',
  'Umm Al Quwain',
  'Fujairah',
]

const cityLookup = new Map(
  CITY_OPTIONS.flatMap((label) => [
    [label.toLowerCase(), label],
    [label.toLowerCase().replaceAll(' ', '-'), label],
  ])
)

function normalizeCityLabel(value) {
  const text = String(value || '').trim()
  if (!text || ['all', 'all cities'].includes(text.toLowerCase())) return ''
  return cityLookup.get(text.toLowerCase()) || titleCase(text.replaceAll('-', ' '))
}

function normalizeCitySelection(value) {
  const values = Array.isArray(value) ? value : [value]
  return Array.from(new Set(values.map(normalizeCityLabel).filter(Boolean)))
}

function selectedRuleCities(alert) {
  const cities = normalizeCitySelection(alert.cities || [])
  if (cities.length) return cities
  return normalizeCitySelection(alert.city)
}

function titleCase(value) {
  return String(value || '').replace(/\b\w/g, (char) => char.toUpperCase())
}

function statusBadge(status) {
  const normalized = String(status || '').toLowerCase()
  if (normalized.includes('error')) return 'bg-rose-500/10 text-rose-200 border-rose-400/25'
  if (normalized.includes('matched') || normalized.includes('baseline') || normalized.includes('sent')) return 'bg-emerald-500/10 text-emerald-200 border-emerald-400/25'
  if (normalized.includes('enabled') || normalized.includes('active') || normalized.includes('ready')) return 'bg-blue-500/10 text-blue-200 border-blue-400/25'
  return 'bg-slate-800 text-slate-300 border-slate-700'
}

function ruleSummary(alert) {
  const formatText = formatRuleFormats(alert)
  const format = formatText !== 'Any format' ? ` Format: ${formatText}.` : ''
  const city = selectedRuleCities(alert).join(', ') || 'all cities'
  if (alert.send_all_new_plates) return `Every new plate from ${city} will be sent to Telegram.${format}`
  const number = alert.plate_number ? `${alert.search_mode} ${alert.plate_number}` : 'any plate number'
  const price = alert.price_max ? ` under AED ${alert.price_max}` : ''
  return `${city} plates matching ${number}${price}.${format}`
}

function formatInterval(seconds) {
  if (seconds < 60) return `${seconds} seconds`
  const minutes = Math.round(seconds / 60)
  return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
}

function formatRuleInterval(alert) {
  const seconds = Number(alert.monitoring_interval_seconds || alert.check_interval_seconds || 0)
  if (seconds > 0) return formatInterval(seconds)
  const minutes = Number(alert.check_interval_minutes || 0)
  if (minutes > 0) return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
  return 'Not set'
}

function intervalDisplay(alert) {
  const seconds = Number(alert.monitoring_interval_seconds || alert.check_interval_seconds || 0)
  const custom = alert.monitoring_interval_mode === 'custom' || (seconds > 0 && !presetIntervalSeconds.includes(seconds))
  return custom && seconds > 0 ? `Custom — every ${formatInterval(seconds)}` : formatInterval(seconds || 20)
}

function normalizeIntervalFields(alert) {
  const seconds = Number(alert.monitoring_interval_seconds || alert.check_interval_seconds || 20)
  const custom = alert.monitoring_interval_mode === 'custom' || !presetIntervalSeconds.includes(seconds)
  const unit = custom && seconds % 60 === 0 ? 'minutes' : 'seconds'
  const value = custom ? (unit === 'minutes' ? seconds / 60 : seconds) : ''
  return {
    ...alert,
    check_interval_seconds: seconds,
    monitoring_interval_seconds: seconds,
    monitoring_interval_mode: custom ? 'custom' : 'preset',
    custom_interval_unit: unit,
    custom_interval_value: value ? String(value) : '',
  }
}

function formatRuleCities(alert) {
  return selectedRuleCities(alert).join(', ') || 'All cities'
}

function formatRulePlate(alert) {
  if (alert.plate_number) return alert.plate_number
  if (alert.contains) return `Contains ${alert.contains}`
  if (alert.starts_with) return `Starts ${alert.starts_with}`
  if (alert.ends_with) return `Ends ${alert.ends_with}`
  return 'Any plate'
}

function isAlertEnabled(alert) {
  const value = alert?.enabled
  if (typeof value === 'string') return ['true', '1', 'yes', 'enabled', 'on'].includes(value.toLowerCase())
  return Boolean(value)
}

function groupedNumberFormats(options = []) {
  const groups = {
    General: [],
    '5 Digits': [],
    '4 Digits': [],
    '3 Digits': [],
  }
  options.forEach((option) => {
    const value = String(option || '').trim()
    if (!value) return
    if (value.includes('(5 Digits)')) groups['5 Digits'].push(value)
    else if (value.includes('(4 Digits)')) groups['4 Digits'].push(value)
    else if (value.includes('(3 Digits)')) groups['3 Digits'].push(value)
    else groups.General.push(value)
  })
  return groups
}

function numberFormatValue(label) {
  const text = String(label || '').trim()
  if (!text || text === 'Any format') return ''
  const repeat = text.match(/^Contains digit repeated (\d+) times$/)
  if (repeat) return `repeat_${repeat[1]}`
  const pattern = text.match(/^(.+) \((\d+) Digits\)$/)
  if (pattern) return `${pattern[1]}_${pattern[2]}`
  return text
}

function flattenNumberFormats(groups) {
  const options = [{ value: '', label: 'Any format', group: 'General' }]
  Object.entries(groups).forEach(([group, items]) => {
    items.forEach((label) => {
      if (label === 'Any format') return
      options.push({ value: numberFormatValue(label), label, group })
    })
  })
  return options.filter((item, index, all) => all.findIndex((other) => other.value === item.value && other.label === item.label) === index)
}

function normalizeNumberFormatValues(value, fallback = '') {
  const raw = Array.isArray(value) ? value : (value ? [value] : [])
  const values = raw
    .map((item) => numberFormatValue(item))
    .filter(Boolean)
  if (!values.length && fallback && fallback !== 'Any format') values.push(numberFormatValue(fallback))
  return Array.from(new Set(values.filter(Boolean)))
}

function numberFormatLabels(value, fallback, options = []) {
  const selected = normalizeNumberFormatValues(value, fallback)
  const labelByValue = new Map(options.map((item) => [item.value, item.label]))
  return selected.map((item) => labelByValue.get(item) || item)
}

function formatRuleFormats(alert, options = [], compact = false) {
  const labels = numberFormatLabels(alert.number_formats, alert.number_format, options)
  if (!labels.length) return 'Any format'
  if (compact && labels.length > 3) return `${labels.length} selected`
  return labels.join(', ')
}

function formatRuleTimestamp(value) {
  if (!value) return 'Never'
  return String(value).replace('T', ' ').replace(/\.\d+Z?$/, '').trim()
}

function formatRuleTime(value) {
  if (!value) return 'Never'
  const clean = String(value).replace('T', ' ').replace(/\.\d+Z?$/, '').trim()
  const parts = clean.match(/\b(\d{1,2}):(\d{2})(?::\d{2})?\b/)
  if (!parts) return clean
  const hour = Number(parts[1])
  const suffix = hour >= 12 ? 'PM' : 'AM'
  const displayHour = hour % 12 || 12
  return `${displayHour}:${parts[2]} ${suffix}`
}

function formatCompactInterval(alert) {
  const seconds = Number(alert.monitoring_interval_seconds || alert.check_interval_seconds || 20)
  if (seconds < 60) return `${seconds} sec`
  const minutes = Math.round(seconds / 60)
  return `${minutes} min`
}

function seenCount(alert) {
  return new Set([...(alert.seen_listing_keys || []), ...(alert.seen_listing_ids || []), ...(alert.seen_listing_urls || [])]).size
}

function normalizeAlertsResponse(data) {
  const alertsList = Array.isArray(data) ? data : data?.alerts || []
  console.log("GET /api/alerts raw:", data)
  console.log("Normalized alerts:", alertsList)
  return Array.isArray(alertsList) ? alertsList : []
}

function Card({ title, helper, icon: Icon, action, children, className = '' }) {
  return (
    <section className={`rounded-[26px] bg-slate-950/55 p-5 shadow-xl shadow-black/10 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-black text-white">{Icon && <Icon size={19} className="text-purple-200" />}{title}</h2>
          {helper && <p className="mt-1.5 max-w-3xl text-sm leading-6 text-slate-400">{helper}</p>}
        </div>
        {action}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  )
}

function Field({ label, children, helper }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</span>
      {children}
      {helper && <span className="mt-2 block text-xs leading-5 text-slate-500">{helper}</span>}
    </label>
  )
}

function ToggleRow({ icon: Icon, title, description, checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`flex w-full items-center gap-4 rounded-2xl px-4 py-3 text-left transition ${
        checked ? 'bg-purple-500/12 ring-1 ring-purple-300/25' : 'bg-slate-900/70 hover:bg-slate-900'
      }`}
    >
      {Icon && <span className={`rounded-xl p-2 ${checked ? 'bg-purple-400/20 text-purple-100' : 'bg-slate-800 text-slate-400'}`}><Icon size={17} /></span>}
      <span className="min-w-0 flex-1">
        <span className="block font-bold text-white">{title}</span>
        {description && <span className="mt-1 block text-sm leading-5 text-slate-400">{description}</span>}
      </span>
      <span className={`relative h-6 w-11 rounded-full transition ${checked ? 'bg-purple-400' : 'bg-slate-700'}`}>
        <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${checked ? 'left-6' : 'left-1'}`} />
      </span>
    </button>
  )
}

function InstagramSection({ title, children }) {
  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-900/55 p-4">
      <h3 className="text-sm font-black uppercase tracking-[0.14em] text-slate-400">{title}</h3>
      <div className="mt-4 space-y-3">{children}</div>
    </div>
  )
}

function DetailPanel({ listing, log }) {
  const rows = listing ? [
    ['Plate', `${listing.city || '?'} ${listing.code || '?'} ${listing.plate_number || '?'}`],
    ['City', listing.city],
    ['Code', listing.code],
    ['Number', listing.plate_number],
    ['Price', listing.price],
    ['Seller', listing.seller_name],
    ['Username', listing.seller_username],
    ['Phone', listing.phone_number],
    ['Posted', `${listing.uploaded_date || ''} ${listing.uploaded_time || ''}`.trim()],
    ['Listing URL', listing.listing_link || listing.post_url],
  ] : []
  return (
    <aside className="w-full xl:sticky xl:top-6 xl:w-72 xl:self-start">
      <div className="rounded-[26px] bg-slate-950/65 p-5 shadow-xl shadow-black/15">
        <h2 className="text-lg font-black text-white">Details</h2>
        {!listing && !log ? (
          <div className="mt-4 rounded-2xl bg-slate-900/70 p-5 text-sm leading-6 text-slate-400">
            Select a listing or log to see details.
          </div>
        ) : (
          <div className="mt-4 space-y-3 text-sm">
            {log && (
              <div className="rounded-2xl bg-slate-900/70 p-3">
                <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Log</p>
                <p className="mt-1 font-bold text-white">{log.event_type || titleCase(log.status) || 'Event'}</p>
                <p className="mt-1 break-words text-slate-400">{log.message}</p>
              </div>
            )}
            {rows.map(([label, value]) => (
              <div key={label} className="rounded-2xl bg-slate-900/70 p-3">
                <p className="text-xs uppercase tracking-[0.14em] text-slate-500">{label}</p>
                <p className="mt-1 break-words font-medium text-slate-100">{value || 'Not available'}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

export default function Alerts({ options = {} }) {
  const [activeTab, setActiveTab] = useState('Alert Rules')
  const [alertsList, setAlertsList] = useState([])
  const [logs, setLogs] = useState([])
  const [settings, setSettings] = useState({})
  const [form, setForm] = useState(DEFAULT_ALERT)
  const [editing, setEditing] = useState(null)
  const [message, setMessage] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)
  const [openMoreRuleId, setOpenMoreRuleId] = useState(null)
  const [expandedAdvancedRuleId, setExpandedAdvancedRuleId] = useState(null)
  const [confirmClearLogs, setConfirmClearLogs] = useState(false)
  const [saving, setSaving] = useState(false)
  const [workingAlertId, setWorkingAlertId] = useState(null)
  const [workingAction, setWorkingAction] = useState('')
  const [logFilter, setLogFilter] = useState('All')
  const [expandedLog, setExpandedLog] = useState(null)
  const [selectedListing, setSelectedListing] = useState(null)
  const [selectedLog, setSelectedLog] = useState(null)
  const [baselineSuccess, setBaselineSuccess] = useState('')
  const [telegramVerification, setTelegramVerification] = useState(null)
  const [verifyingTelegram, setVerifyingTelegram] = useState(false)
  const [runNowResult, setRunNowResult] = useState(null)
  const [debugScanResult, setDebugScanResult] = useState(null)
  const [instagramSettings, setInstagramSettings] = useState(DEFAULT_INSTAGRAM_SETTINGS)
  const [instagramWorking, setInstagramWorking] = useState('')
  const [instagramProviderStatus, setInstagramProviderStatus] = useState(null)
  const [instagramDirty, setInstagramDirty] = useState(false)
  const [instagramLastSavedAt, setInstagramLastSavedAt] = useState('')
  const [instagramAccountsText, setInstagramAccountsText] = useState('')
  const [formatMenuOpen, setFormatMenuOpen] = useState(false)
  const [formatQuery, setFormatQuery] = useState('')
  const [dailyReportDates, setDailyReportDates] = useState({})

  const mergedOptions = {
    codes: options.codes || CODE_OPTIONS,
    number_formats: options.number_formats || NUMBER_FORMAT_OPTIONS,
    search_modes: options.search_modes || SEARCH_MODE_OPTIONS,
    intervals: options.intervals || ALERT_INTERVAL_OPTIONS,
  }

  const normalizedChannelPreview = normalizeTelegramChannel(settings.telegram_chat_id || settings.telegram_channel_id || '')
  const telegramConfigured = Boolean(settings.telegram_bot_token && normalizedChannelPreview)
  const enabledAlertList = alertsList.filter(isAlertEnabled)
  const enabledRules = enabledAlertList.length
  const multipleAlertsEnabled = enabledRules > 1
  const selectedIntervalSeconds = Number(form.monitoring_interval_seconds || form.check_interval_seconds || (Number(form.check_interval_minutes || 1) * 60) || 20)
  const customIntervalSelected = form.monitoring_interval_mode === 'custom' || !presetIntervalSeconds.includes(selectedIntervalSeconds)
  const numberFormatGroups = groupedNumberFormats(mergedOptions.number_formats)
  const numberFormatOptions = flattenNumberFormats(numberFormatGroups)
  const selectedNumberFormats = normalizeNumberFormatValues(form.number_formats, form.number_format)
  const selectedNumberFormatLabels = numberFormatLabels(selectedNumberFormats, '', numberFormatOptions)
  const formatQueryText = formatQuery.trim().toLowerCase()
  const visibleNumberFormatGroups = Object.fromEntries(Object.entries(numberFormatGroups).map(([group, items]) => [
    group,
    items.filter((item) => !formatQueryText || item.toLowerCase().includes(formatQueryText)),
  ]))
  const instagramAccounts = parseInstagramAccounts(instagramAccountsText || (instagramSettings.accounts || []).map((account) => account.username || account).join('\n'))
  const instagramProviderConfigured = Boolean(
    (instagramSettings.instagram_provider || 'Apify') !== 'Apify' ||
    (instagramSettings.apify_api_token && instagramSettings.apify_actor_id)
  )
  const instagramProviderMissingReason = instagramProviderConfigured ? '' : 'Add API token and actor ID, then save settings.'
  const instagramSendingEnabled = Boolean(instagramSettings.enabled && instagramSettings.send_all_new_posts)
  const instagramIntervalMinutes = Number(instagramSettings.check_interval_minutes || 10)
  const instagramTelegramStatus = telegramConfigured ? 'Telegram sending is configured.' : 'Telegram sending is not configured.'
  const instagramStatusMessage = !instagramSettings.enabled
    ? 'Instagram monitoring is disabled. Turn it on to check accounts.'
    : !instagramSettings.send_all_new_posts
      ? 'Instagram post sending is disabled. New posts will not be sent to Telegram automatically.'
      : `Instagram posts are enabled for ${instagramAccounts.length} ${instagramAccounts.length === 1 ? 'account' : 'accounts'}.`
  const instagramStatusDetail = instagramSendingEnabled
    ? `Only posts uploaded after activation will be sent. New uploaded posts from these accounts will be sent to Telegram every ${instagramIntervalMinutes} ${instagramIntervalMinutes === 1 ? 'minute' : 'minutes'}.`
    : instagramTelegramStatus

  const preparedLogs = useMemo(() => {
    if (logFilter === 'All') return logs
    const filter = logFilter.toLowerCase()
    return logs.filter((log) => {
      const severity = String(log.severity || '').toLowerCase()
      const status = String(log.status || '').toLowerCase()
      const event = String(log.event_type || '').toLowerCase()
      const text = String(log.message || '').toLowerCase()
      if (filter === 'success') return severity === 'success' || Number(log.sent_notifications || 0) > 0
      if (filter === 'sent') return event === 'sent' || Number(log.sent_notifications || 0) > 0 || text.includes('sent')
      if (filter === 'skipped') return event === 'skipped' || text.includes('skipped')
      if (filter === 'match') return event === 'match' || status.includes('matched') || text.includes('match')
      if (filter === 'no match') return event === 'no match' || status.includes('no_match') || text.includes('no match')
      return severity === filter || status.includes(filter) || event === filter
    })
  }, [logs, logFilter])

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    try {
      const [alertResponse, logResponse, settingsResponse, instagramResponse] = await Promise.all([getAlerts(), getAlertLogs(), api.settings(), api.getInstagramSettings()])
      const alertsList = normalizeAlertsResponse(alertResponse)
      console.log("Reloaded alerts:", alertsList)
      setAlertsList(alertsList)
      setLogs(logResponse.logs || [])
      setSettings(settingsResponse.settings || {})
      const nextInstagramSettings = { ...DEFAULT_INSTAGRAM_SETTINGS, ...(instagramResponse.settings || {}) }
      setInstagramSettings(nextInstagramSettings)
      setInstagramAccountsText((nextInstagramSettings.accounts || []).map((account) => account.username || account).join('\n'))
      setInstagramDirty(false)
      return alertsList
    } catch {
      setMessage('Failed to load alerts and logs.')
      return []
    }
  }

  function updateField(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function updateCities(cities) {
    const normalizedCities = normalizeCitySelection(cities)
    setForm((current) => ({
      ...current,
      cities: normalizedCities,
      city: normalizedCities[0] || '',
    }))
  }

  function updateNumberFormats(nextValue) {
    setForm((current) => {
      if (!nextValue) return { ...current, number_formats: [], number_format: 'Any format' }
      const currentValues = normalizeNumberFormatValues(current.number_formats, current.number_format)
      const exists = currentValues.includes(nextValue)
      const nextValues = exists ? currentValues.filter((item) => item !== nextValue) : [...currentValues, nextValue]
      const labels = numberFormatLabels(nextValues, '', numberFormatOptions)
      return {
        ...current,
        number_formats: nextValues,
        number_format: labels[0] || 'Any format',
      }
    })
  }

  function updateSettingsField(key, value) {
    setSettings((current) => ({ ...current, [key]: value }))
    setTelegramVerification(null)
  }

  function updateInstagramField(key, value) {
    setInstagramSettings((current) => ({ ...current, [key]: value }))
    setInstagramDirty(true)
  }

  function normalizeInstagramUsername(value) {
    return String(value || '')
      .trim()
      .replace(/^https?:\/\/(?:www\.)?instagram\.com\//i, '')
      .split('?')[0]
      .replace(/\/+$/, '')
      .replace(/^@/, '')
      .toLowerCase()
  }

  function parseInstagramAccounts(value, { sort = false } = {}) {
    const seen = new Set()
    const usernames = String(value || '')
      .split(/[\n,]+/)
      .map(normalizeInstagramUsername)
      .filter(Boolean)
      .filter((username) => {
        if (seen.has(username)) return false
        seen.add(username)
        return true
      })
    if (sort) usernames.sort((a, b) => a.localeCompare(b))
    return usernames.map((username) => ({ username, enabled: true }))
  }

  function updateInstagramAccounts(value) {
    setInstagramAccountsText(value)
    setInstagramDirty(true)
  }

  function updateInstagramAccountsList(accounts) {
    setInstagramAccountsText(accounts.map((account) => account.username || account).join('\n'))
    setInstagramSettings((current) => ({ ...current, accounts }))
    setInstagramDirty(true)
  }

  function clearInstagramAccounts() {
    updateInstagramAccountsList([])
  }

  function removeDuplicateInstagramAccounts() {
    updateInstagramAccountsList(parseInstagramAccounts(instagramAccounts.map((account) => account.username || account).join('\n')))
  }

  function sortInstagramAccounts() {
    updateInstagramAccountsList(parseInstagramAccounts(instagramAccounts.map((account) => account.username || account).join('\n'), { sort: true }))
  }

  function normalizeTelegramChannel(value) {
    let text = String(value || '').trim()
    text = text.replace(/^https?:\/\/t\.me\//i, '').replace(/^t\.me\//i, '').replace(/\/+$/, '')
    if (text && !text.startsWith('@') && !text.startsWith('-100') && !/^-?\d+$/.test(text)) text = `@${text}`
    return text
  }

  async function saveTelegramSettings() {
    const payload = { ...settings, telegram_chat_id: normalizeTelegramChannel(settings.telegram_chat_id || settings.telegram_channel_id || '') }
    try {
      const response = await api.saveSettings(payload)
      setSettings(response.settings || payload)
      setMessage('Telegram settings saved.')
    } catch (error) {
      setMessage(error?.message || 'Failed to save Telegram settings.')
    }
  }

  async function verifyTelegramConnection() {
    setVerifyingTelegram(true)
    setMessage('')
    try {
      const response = await api.verifyTelegram({
        telegram_bot_token: settings.telegram_bot_token || '',
        telegram_chat_id: settings.telegram_chat_id || settings.telegram_channel_id || '',
      })
      setTelegramVerification(response)
      setMessage(response.message || (response.ok ? 'Telegram connection verified.' : 'Telegram connection is not ready.'))
    } catch (error) {
      setTelegramVerification({ ok: false, message: error.message })
      setMessage(error.message || 'Telegram verification failed.')
    } finally {
      setVerifyingTelegram(false)
    }
  }

  async function saveInstagramSettings(nextSettings = instagramSettings) {
    setInstagramWorking('save')
    setMessage('')
    const cleanedSettings = {
      ...nextSettings,
      accounts: parseInstagramAccounts(instagramAccountsText || (nextSettings.accounts || []).map((account) => account.username || account).join('\n')),
    }
    try {
      const response = await api.saveInstagramSettings(cleanedSettings)
      const savedSettings = { ...DEFAULT_INSTAGRAM_SETTINGS, ...(response.settings || {}) }
      setInstagramSettings(savedSettings)
      setInstagramAccountsText((savedSettings.accounts || []).map((account) => account.username || account).join('\n'))
      setInstagramDirty(false)
      setInstagramLastSavedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
      setMessage(response.message || 'Instagram monitoring settings saved.')
      await loadAll()
    } catch (error) {
      setMessage(error?.message || 'Failed to save Instagram settings.')
    } finally {
      setInstagramWorking('')
    }
  }

  async function runInstagramAction(actionName, request, successFallback) {
    setInstagramWorking(actionName)
    setMessage('')
    try {
      await api.saveInstagramSettings({
        ...instagramSettings,
        accounts: parseInstagramAccounts(instagramAccountsText),
      })
      const response = await request()
      setMessage(response.message || successFallback)
      await loadAll()
    } catch (error) {
      setMessage(error?.message || 'Instagram action failed.')
    } finally {
      setInstagramWorking('')
    }
  }

  async function verifyInstagramProvider() {
    setInstagramWorking('verify-provider')
    setMessage('')
    try {
      const response = await api.verifyInstagramProvider(instagramSettings)
      setInstagramProviderStatus(response)
      setInstagramSettings((current) => ({
        ...current,
        provider_connected: response.provider_connected,
        last_provider_error: response.last_provider_error || '',
      }))
      setMessage(response.provider_connected ? 'Instagram provider verified.' : response.last_provider_error || 'Instagram provider verification failed.')
      await loadAll()
    } catch (error) {
      setMessage(error?.message || 'Instagram provider verification failed.')
    } finally {
      setInstagramWorking('')
    }
  }

  function updateInterval(seconds) {
    setForm((current) => ({
      ...current,
      check_interval_seconds: Number(seconds),
      monitoring_interval_seconds: Number(seconds),
      check_interval_minutes: Math.max(1, Math.round(Number(seconds) / 60)),
      monitoring_interval_mode: 'preset',
    }))
  }

  function updateImmediateMode(value) {
    setForm((current) => ({
      ...current,
      immediate_alerts_mode: value,
      check_interval_seconds: value ? 20 : current.check_interval_seconds,
      monitoring_interval_seconds: value ? 20 : current.monitoring_interval_seconds,
      check_interval_minutes: value ? 1 : current.check_interval_minutes,
      monitoring_interval_mode: value ? 'preset' : current.monitoring_interval_mode,
      fresh_listing_window_minutes: value ? 15 : current.fresh_listing_window_minutes,
      max_pages_per_scan: value ? 20 : current.max_pages_per_scan,
      max_listings_per_scan: value ? 1000 : current.max_listings_per_scan,
    }))
  }

  function selectCustomInterval() {
    setForm((current) => {
      const unit = current.custom_interval_unit || 'seconds'
      const value = current.custom_interval_value || (unit === 'minutes' ? '2' : '45')
      const seconds = unit === 'minutes' ? Number(value) * 60 : Number(value)
      return {
        ...current,
        monitoring_interval_mode: 'custom',
        custom_interval_value: value,
        custom_interval_unit: unit,
        check_interval_seconds: seconds,
        monitoring_interval_seconds: seconds,
        check_interval_minutes: Math.max(1, Math.round(seconds / 60)),
      }
    })
  }

  function updateCustomInterval(value, unit = form.custom_interval_unit || 'seconds') {
    const numeric = Number(value || 0)
    const seconds = unit === 'minutes' ? numeric * 60 : numeric
    setForm((current) => ({
      ...current,
      monitoring_interval_mode: 'custom',
      custom_interval_value: value,
      custom_interval_unit: unit,
      check_interval_seconds: seconds,
      monitoring_interval_seconds: seconds,
      check_interval_minutes: Math.max(1, Math.round((seconds || 60) / 60)),
    }))
  }

  function validateInterval(alert) {
    const seconds = Number(alert.monitoring_interval_seconds || alert.check_interval_seconds || 0)
    if (seconds < 10) return 'Minimum interval is 10 seconds.'
    if (seconds > 3600) return 'Maximum interval is 60 minutes.'
    return ''
  }

  function resetForm({ clearMessage = true } = {}) {
    setForm(DEFAULT_ALERT)
    setEditing(null)
    if (clearMessage) setMessage('')
    setFormatMenuOpen(false)
    setFormatQuery('')
  }

  async function handleSave() {
    setSaving(true)
    setMessage('')
    try {
      const intervalError = validateInterval(form)
      if (intervalError) {
        setMessage(intervalError)
        return
      }
      const sendAll = form.search_mode === 'Send all new plates' || form.send_all_new_plates === true
      const selectedCities = selectedRuleCities(form)
      const selectedCity = selectedCities[0] || ''
      console.log("Creating alert with city:", selectedCity)
      const payload = {
        ...form,
        send_all_new_plates: sendAll,
        city: selectedCity,
        cities: selectedCities,
        code: form.code,
        plate_number: form.plate_number,
        contains: form.contains,
        starts_with: form.starts_with,
        ends_with: form.ends_with,
        price_max: form.price_max,
        number_formats: selectedNumberFormats,
        number_format: selectedNumberFormatLabels[0] || 'Any format',
        monitoring_interval_seconds: selectedIntervalSeconds,
        check_interval_seconds: selectedIntervalSeconds,
      }
      console.log("Creating alert payload:", payload)
      if (editing) {
        const createResponse = await updateAlert(editing, payload)
        console.log("Create alert response:", createResponse)
        setMessage(createResponse.message || 'Alert updated successfully.')
      } else {
        const createResponse = await createAlert(payload)
        console.log("Create alert response:", createResponse)
        setMessage(createResponse.message || 'Alert created. Future matching plates will be sent automatically.')
      }
      resetForm({ clearMessage: false })
      await loadAll()
    } catch (error) {
      setMessage(error?.message || 'Failed to save alert.')
    } finally {
      setSaving(false)
    }
  }

  function beginEdit(alert) {
    const cities = selectedRuleCities(alert)
    setEditing(alert.id)
    const formats = normalizeNumberFormatValues(alert.number_formats, alert.number_format)
    setForm(normalizeIntervalFields({ ...DEFAULT_ALERT, ...alert, city: cities[0] || '', cities, number_formats: formats, number_format: formatRuleFormats({ ...alert, number_formats: formats }, numberFormatOptions).split(', ')[0] || 'Any format' }))
    setActiveTab('Alert Rules')
    setMessage('')
    setFormatMenuOpen(false)
    setFormatQuery('')
  }

  async function withWorking(alert, action, successMessage, actionName = 'working') {
    setWorkingAlertId(alert.id)
    setWorkingAction(actionName)
    setMessage('')
    try {
      const response = await action()
      if (actionName === 'run' || actionName === 'force') setRunNowResult(response)
      setMessage(typeof successMessage === 'function' ? successMessage(response) : successMessage)
      await loadAll()
    } catch (error) {
      const errorMessage = actionName.startsWith('daily-report')
        ? friendlyDailyReportError(error)
        : error?.message || 'Action failed.'
      if (actionName === 'run' || actionName === 'force') setRunNowResult({ ok: false, message: errorMessage })
      setMessage(actionName === 'test' && errorMessage.toLowerCase().startsWith('telegram test failed') ? errorMessage : `${actionName === 'test' ? 'Telegram test failed: ' : ''}${errorMessage}`)
    } finally {
      setWorkingAlertId(null)
      setWorkingAction('')
    }
  }

  function handleRunNow(alert) {
    setRunNowResult({ ok: true, message: 'Scanning listings and preparing Telegram decision...' })
    withWorking(alert, () => runAlertNow(alert.id), (response) => {
      const result = response.result || {}
      return response.message || result.message || `Run completed: ${result.sent ?? 0} sent.`
    }, 'run')
  }

  function handleDebugScan(alert) {
    setDebugScanResult({ alertId: alert.id, message: 'Running debug scan...' })
    withWorking(alert, async () => {
      const response = await debugAlertScan(alert.id)
      setDebugScanResult({ alertId: alert.id, ...response })
      return response
    }, (response) => response.message || 'Debug scan completed.', 'debug')
  }

  function handleResetBaseline(alert) {
    withWorking(alert, async () => {
      const response = await resetAlertBaseline(alert.id)
      setBaselineSuccess('Baseline reset successfully. Future listings only.')
      if (response.alert) {
        const cities = selectedRuleCities(response.alert)
        const formats = normalizeNumberFormatValues(response.alert.number_formats, response.alert.number_format)
        setForm((current) => ({ ...current, ...response.alert, city: cities[0] || '', cities, number_formats: formats }))
      }
      return response
    }, (response) => response.message || 'Baseline reset. Future listings only.', 'baseline')
  }

  function handleTestTelegram(alert) {
    withWorking(alert, () => testTelegram(alert.id), (response) => response.message || 'Test message sent to Telegram channel.', 'test')
  }

  function dailyReportDate(alertId) {
    return dailyReportDates[alertId] || defaultDailyReportDate
  }

  function handleSendDailyReport(alert) {
    const date = dailyReportDate(alert.id)
    setOpenMoreRuleId(null)
    withWorking(
      alert,
      () => sendDailyRuleReport(alert.id, date),
      (response) => response.message || `Daily Excel report sent for ${date}.`,
      'daily-report-send',
    )
  }

  function handleDownloadDailyReport(alert) {
    const date = dailyReportDate(alert.id)
    setOpenMoreRuleId(null)
    withWorking(
      alert,
      () => downloadDailyRuleReport(alert.id, date),
      (response) => `Daily Excel downloaded: ${response.filename}`,
      'daily-report-download',
    )
  }

  async function handleTestChannelAlert() {
    setWorkingAction('test-channel')
    setMessage('')
    try {
      const response = await testTelegramChannel({
        telegram_bot_token: settings.telegram_bot_token || '',
        telegram_chat_id: settings.telegram_chat_id || settings.telegram_channel_id || '',
      })
      setMessage(response.message || 'Test message sent to Telegram channel.')
    } catch (error) {
      setMessage(error?.message || 'Telegram channel test failed.')
    } finally {
      setWorkingAction('')
    }
  }

  function handleDisableOthers(alert) {
    withWorking(alert, () => disableOtherAlerts(alert.id), (response) => response.message || 'Other alerts disabled.', 'safety')
  }

  function handleForceSendTestListing(alert) {
    setRunNowResult({ ok: true, message: 'Sending a sample listing directly to Telegram...' })
    withWorking(alert, () => forceSendTestListing(alert.id), (response) => response.message || 'Force test listing sent to Telegram channel.', 'force')
  }

  async function confirmDelete(alertId = pendingDelete) {
    if (!alertId) return
    try {
      await deleteAlert(alertId)
      setPendingDelete(null)
      setMessage('Alert deleted.')
      await loadAll()
    } catch (error) {
      setMessage(error?.message || 'Failed to delete alert.')
    }
  }

  async function confirmClearLogsHandler() {
    try {
      await clearAlertLogs()
      setLogs([])
      setConfirmClearLogs(false)
      setMessage('Alert logs cleared.')
    } catch (error) {
      setMessage(error?.message || 'Failed to clear logs.')
    }
  }

  async function handleStopAllAlerts() {
    setWorkingAction('stop-all')
    setMessage('')
    try {
      const response = await stopAllAlerts()
      setMessage(response.message || 'Emergency stop complete. All alerts disabled.')
      await loadAll()
    } catch (error) {
      setMessage(error?.message || 'Failed to stop alerts.')
    } finally {
      setWorkingAction('')
    }
  }

  function showLogDetails(log) {
    setExpandedLog(expandedLog === log.id ? null : log.id)
    setSelectedLog(log)
    if (log.listing && Object.keys(log.listing).length) setSelectedListing(log.listing)
  }

  const testTarget = editing ? (alertsList.find((alert) => alert.id === editing) || { id: editing }) : alertsList[0]
  const monitoringSpeedCard = (
    <Card title="Monitoring Speed" helper="Choose how often this alert checks for new matching listings." icon={Gauge}>
      <div className="grid gap-3 grid-cols-3 md:grid-cols-6 2xl:grid-cols-3">
        {intervalPresets.map((preset) => {
          const active = !customIntervalSelected && selectedIntervalSeconds === preset.seconds
          return (
            <button key={preset.seconds} className={`rounded-2xl border py-3 px-2 text-center transition ${active ? 'border-purple-300/40 bg-purple-500 text-white shadow-lg shadow-purple-950/25' : 'border-slate-800 bg-slate-900/70 text-slate-300 hover:bg-slate-900'}`} onClick={() => updateInterval(preset.seconds)}>
              <span className="block text-base font-black whitespace-nowrap">{preset.label}</span>
            </button>
          )
        })}
        <button className={`rounded-2xl border py-3 px-2 text-center transition ${customIntervalSelected ? 'border-purple-300/40 bg-purple-500 text-white shadow-lg shadow-purple-950/25' : 'border-slate-800 bg-slate-900/70 text-slate-300 hover:bg-slate-900'}`} onClick={selectCustomInterval}>
          <span className="block text-base font-black whitespace-nowrap">Custom</span>
        </button>
      </div>
      {customIntervalSelected && (
        <div className="mt-4 grid gap-3 rounded-2xl bg-slate-900/70 p-4 sm:grid-cols-[minmax(0,1fr)_10rem]">
          <Field label="Custom interval">
            <input className="input" type="number" min="1" value={form.custom_interval_value || ''} onChange={(event) => updateCustomInterval(event.target.value, form.custom_interval_unit || 'seconds')} placeholder="Enter time" />
          </Field>
          <Field label="Unit">
            <select className="input" value={form.custom_interval_unit || 'seconds'} onChange={(event) => updateCustomInterval(form.custom_interval_value || '', event.target.value)}>
              <option value="seconds">seconds</option>
              <option value="minutes">minutes</option>
            </select>
          </Field>
        </div>
      )}
      <div className="mt-4 rounded-2xl bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
        Current interval: <span className="font-bold text-white">Every {formatInterval(selectedIntervalSeconds)}{customIntervalSelected ? ' (Custom)' : ''}</span>
      </div>
    </Card>
  )

  const savedRulesCard = (
    <Card
      title="Saved Rules"
      helper="Compact monitoring status for each alert rule."
      icon={FileText}
      className="h-fit"
      action={<button className="btn-danger" onClick={handleStopAllAlerts} disabled={!alertsList.length || workingAction === 'stop-all'}><AlertTriangle size={14} /> {workingAction === 'stop-all' ? 'Stopping...' : 'Stop all'}</button>}
    >
      <div className="space-y-3">
        {multipleAlertsEnabled && (
          <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 p-4 text-sm font-bold text-amber-100">
            Multiple alerts are enabled. Plates may be sent from more than one rule.
          </div>
        )}
        {alertsList.length === 0 ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 text-sm leading-6 text-slate-400">
            No alert rules yet. Create your first alert to start monitoring.
          </div>
        ) : alertsList.map((alert) => {
          const ready = Boolean((alert.telegram_bot_token || settings.telegram_bot_token) && (alert.telegram_chat_id || settings.telegram_chat_id || settings.telegram_channel_id))
          const enabled = isAlertEnabled(alert)
          const badgeLabel = !ready ? 'Telegram not ready' : enabled ? 'Enabled' : 'Disabled'
          const moreOpen = openMoreRuleId === alert.id
          const advancedOpen = expandedAdvancedRuleId === alert.id
          const formatSummary = formatRuleFormats(alert, numberFormatOptions, true)
          const formatDetails = formatRuleFormats(alert, numberFormatOptions)
          const mainRows = [
            ['City', formatRuleCities(alert)],
            ['Code', alert.code || 'Any'],
            ['Plate / keyword', formatRulePlate(alert)],
            ['Format', formatSummary],
            ['Interval', formatCompactInterval(alert)],
          ]
          const statusRows = [
            ['Last scan', formatRuleTime(alert.last_scan_at || alert.last_checked_at)],
            ['Last sent', formatRuleTime(alert.last_sent_at)],
            ['Sent today', alert.sent_today || 0],
          ]
          const advancedRows = [
            ['Baseline status', alert.baseline_created && alert.baseline_completed ? 'Ready' : 'Creating on next run'],
            ['Seen count', seenCount(alert)],
            ['Number formats', formatDetails],
            ['Last scan result', alert.last_status || 'Never'],
            ['Last skip reason', alert.last_skip_reason || 'None'],
            ['Pages scanned', alert.last_pages_scanned || 0],
            ['Listings found', alert.last_listings_found || 0],
          ]
          return (
            <div key={alert.id} className="rounded-2xl border border-slate-800/80 bg-slate-900/70 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="min-w-0 truncate font-black text-white">{alert.name || 'Untitled alert'}</h3>
                <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-bold ${statusBadge(badgeLabel)}`}>{badgeLabel}</span>
              </div>
              <div className="mt-4 grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
                {mainRows.map(([label, value]) => (
                  <div key={label} className="flex min-w-0 justify-between gap-4 border-b border-slate-800/70 py-2">
                    <span className="shrink-0 text-slate-500">{label}</span>
                    <span className="truncate font-bold text-slate-100">{value}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-x-6 gap-y-2 text-sm md:grid-cols-3">
                {statusRows.map(([label, value]) => (
                  <div key={label} className="flex min-w-0 justify-between gap-4 rounded-xl bg-slate-950/35 px-3 py-2">
                    <span className="shrink-0 text-slate-500">{label}</span>
                    <span className="truncate font-bold text-slate-100">{value}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button className="btn-muted" onClick={() => beginEdit(alert)}>Edit</button>
                <button className="btn-muted" onClick={() => withWorking(alert, () => toggleAlert(alert.id), (response) => response.message || `${enabled ? 'Disabled' : 'Enabled'} ${alert.name}`, 'toggle')} disabled={workingAlertId === alert.id}>{workingAlertId === alert.id && workingAction === 'toggle' ? 'Updating...' : enabled ? 'Disable' : 'Enable'}</button>
                <button className="btn-muted" onClick={() => handleRunNow(alert)} disabled={workingAlertId === alert.id}><Play size={14} /> {workingAlertId === alert.id && workingAction === 'run' ? 'Running...' : 'Run now'}</button>
                <button className="btn-muted" onClick={() => handleDebugScan(alert)} disabled={workingAlertId === alert.id}><Search size={14} /> {workingAlertId === alert.id && workingAction === 'debug' ? 'Scanning...' : 'Debug'}</button>
                <div className="relative">
                  <button className="btn-muted" onClick={() => setOpenMoreRuleId(moreOpen ? null : alert.id)}><MoreHorizontal size={14} /> More</button>
                  {moreOpen && (
                    <div className="absolute right-0 z-30 mt-2 w-72 rounded-2xl border border-slate-800 bg-slate-950 p-2 shadow-2xl">
                      <label className="block px-3 pb-2 pt-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                        Daily report date
                        <input
                          type="date"
                          className="input mt-2"
                          value={dailyReportDate(alert.id)}
                          onChange={(event) => setDailyReportDates((current) => ({ ...current, [alert.id]: event.target.value }))}
                          onClick={(event) => event.stopPropagation()}
                        />
                      </label>
                      <button className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => handleSendDailyReport(alert)} disabled={!enabled || workingAlertId === alert.id}><Send size={14} /> {workingAlertId === alert.id && workingAction === 'daily-report-send' ? 'Sending Excel...' : 'Send Daily Excel Now'}</button>
                      <button className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => handleDownloadDailyReport(alert)} disabled={!enabled || workingAlertId === alert.id}><Download size={14} /> {workingAlertId === alert.id && workingAction === 'daily-report-download' ? 'Preparing download...' : 'Download Daily Excel'}</button>
                      {!enabled && <p className="px-3 pb-2 text-xs text-amber-300">Enable this rule to generate daily reports.</p>}
                      <div className="my-1 border-t border-slate-800" />
                      <button className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-900" onClick={() => { setOpenMoreRuleId(null); handleResetBaseline(alert) }} disabled={workingAlertId === alert.id}><RefreshCw size={14} /> Reset baseline</button>
                      <button className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-900" onClick={() => { setOpenMoreRuleId(null); handleTestTelegram(alert) }} disabled={workingAlertId === alert.id}><Send size={14} /> Test Telegram</button>
                      <button className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-rose-200 hover:bg-rose-500/10" onClick={() => { setOpenMoreRuleId(null); setPendingDelete(alert.id) }}><Trash2 size={14} /> Delete</button>
                    </div>
                  )}
                </div>
              </div>
              <button className="mt-4 flex items-center gap-2 text-sm font-bold text-slate-300 hover:text-white" onClick={() => setExpandedAdvancedRuleId(advancedOpen ? null : alert.id)}>
                <ChevronDown size={15} className={`transition ${advancedOpen ? 'rotate-180' : ''}`} />
                Advanced details
              </button>
              {advancedOpen && (
                <div className="mt-3 grid gap-x-6 gap-y-2 rounded-2xl bg-slate-950/35 p-4 text-sm md:grid-cols-2">
                  {advancedRows.map(([label, value]) => (
                    <div key={label} className="flex min-w-0 justify-between gap-4 border-b border-slate-800/70 py-2 last:border-0">
                      <span className="shrink-0 text-slate-500">{label}</span>
                      <span className="truncate font-bold text-slate-100">{value}</span>
                    </div>
                  ))}
                </div>
              )}
              {debugScanResult?.alertId === alert.id && (
                <div className="mt-4 rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-200">
                  <p className="font-bold">{debugScanResult.message}</p>
                  <div className="mt-3 max-h-80 overflow-auto space-y-2">
                    {(debugScanResult.debug_listings || []).map((item, index) => (
                      <div key={`${item.url}-${index}`} className="rounded-xl bg-slate-900/80 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="font-bold">{item.plate}</p>
                          <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${item.would_send ? 'bg-emerald-500/15 text-emerald-200' : 'bg-slate-800 text-slate-300'}`}>{item.would_send ? 'Would send' : 'Would skip'}</span>
                        </div>
                        <p className="mt-1 text-slate-400">City: {item.listing_city || '?'} | Posted: {item.posted_text || '?'} | Price: {item.price || '?'}</p>
                        <p className="mt-1 text-slate-400">Listing number: {item.listing_number || '?'} | Selected formats: {(item.selected_formats || []).join(', ') || 'Any format'}</p>
                        <p className="mt-1 text-slate-400">Format matched: {item.format_matched_text || (item.format_matched ? 'yes' : 'no')}{item.matched_format_name ? ` | ${item.matched_format_name}` : ''}</p>
                        <p className="mt-1 break-words text-slate-500">{item.skip_reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {pendingDelete === alert.id && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-rose-500/10 p-4 text-sm text-rose-100">
                  <p className="font-bold">Delete this alert rule?</p>
                  <div className="flex gap-2"><button className="btn-muted" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn-danger" onClick={() => confirmDelete(alert.id)}>Confirm delete</button></div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )

  return (
    <div className="mx-auto max-w-[1500px] space-y-6">
      <section className="rounded-[30px] bg-slate-950/55 p-6 shadow-xl shadow-black/10">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="flex items-start gap-4">
            <span className="rounded-2xl bg-purple-500/15 p-3 text-purple-200"><Bell size={24} /></span>
            <div>
              <h1 className="text-3xl font-black text-white">Alerts Studio</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">Create plate rules, verify Telegram, and monitor alert activity from a cleaner workspace.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <span className={`rounded-full border px-3 py-1.5 font-bold ${statusBadge(telegramConfigured ? 'Ready' : 'Warning')}`}>Telegram {telegramConfigured ? 'configured' : 'missing'}</span>
            <span className="rounded-full border border-slate-700 bg-slate-800 px-3 py-1.5 font-bold text-slate-200">{enabledRules} enabled</span>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap gap-2 rounded-2xl bg-slate-900/60 p-1.5">
          {tabs.map((tab) => (
            <button key={tab} className={`rounded-xl px-4 py-2 text-sm font-bold transition ${activeTab === tab ? 'bg-purple-500 text-white shadow-lg shadow-purple-950/30' : 'text-slate-300 hover:bg-slate-800'}`} onClick={() => setActiveTab(tab)}>{tab}</button>
          ))}
        </div>
      </section>

      {message && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-purple-400/25 bg-purple-500/10 px-5 py-4 text-sm text-purple-100">
          <span>{message}</span>
          <button className="rounded-xl bg-slate-900 px-3 py-1.5 hover:bg-slate-800" onClick={() => setMessage('')}>Dismiss</button>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <main className="min-w-0 space-y-6">
          {activeTab === 'Alert Rules' && (
            <div className="grid items-start gap-6 2xl:grid-cols-[minmax(26rem,36rem)_minmax(0,1fr)]">
              <div className="space-y-6">
                <Card title={editing ? 'Edit Alert Rule' : 'Create Alert Rule'} helper="Define the plate pattern and market filters. Telegram setup lives in its own tab." icon={FileText} className="max-w-[36rem]">
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="Alert name"><input className="input" value={form.name} onChange={(event) => updateField('name', event.target.value)} placeholder="Dubai VIP watch" /></Field>
                    <Field label="City / Emirate"><CityMultiSelect value={form.cities || []} onChange={updateCities} /></Field>
                    <Field label="Code"><select className="input" value={form.code || ''} onChange={(event) => updateField('code', event.target.value === 'Any code' ? '' : event.target.value)}>{mergedOptions.codes.map((item) => <option key={item} value={item === 'Any code' ? '' : item}>{item}</option>)}</select></Field>
                    <Field label="Plate / keyword"><input className="input" value={form.plate_number} onChange={(event) => updateField('plate_number', event.target.value)} placeholder="89898" /></Field>
                    <Field label="Search mode"><select className="input" value={form.search_mode} onChange={(event) => {
                      const value = event.target.value
                      setForm((current) => ({ ...current, search_mode: value, send_all_new_plates: value === 'Send all new plates' }))
                    }}>{['Send all new plates', ...mergedOptions.search_modes].filter((item, index, all) => all.indexOf(item) === index).map((item) => <option key={item}>{item}</option>)}</select></Field>
                    <Field label="Number Format">
                      <div className="relative">
                        <button type="button" className="input flex min-h-[46px] items-center justify-between gap-3 text-left" onClick={() => setFormatMenuOpen((open) => !open)}>
                          <span className="flex min-w-0 flex-1 flex-wrap gap-1.5">
                            {selectedNumberFormatLabels.length ? selectedNumberFormatLabels.slice(0, 3).map((label) => (
                              <span key={label} className="max-w-full truncate rounded-full bg-purple-500/15 px-2 py-1 text-xs font-bold text-purple-100">{label}</span>
                            )) : <span className="text-slate-400">Any format</span>}
                            {selectedNumberFormatLabels.length > 3 && <span className="rounded-full bg-slate-800 px-2 py-1 text-xs font-bold text-slate-200">{selectedNumberFormatLabels.length} selected</span>}
                          </span>
                          <ChevronDown size={16} className={`shrink-0 text-slate-400 transition ${formatMenuOpen ? 'rotate-180' : ''}`} />
                        </button>
                        {formatMenuOpen && (
                          <div className="absolute z-40 mt-2 max-h-80 w-full overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl">
                            <div className="border-b border-slate-800 p-2">
                              <input className="input h-10" value={formatQuery} onChange={(event) => setFormatQuery(event.target.value)} placeholder="Search formats" />
                            </div>
                            <div className="max-h-64 overflow-auto p-2">
                              <button type="button" className={`mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm ${selectedNumberFormats.length === 0 ? 'bg-purple-500/20 text-purple-100' : 'text-slate-200 hover:bg-slate-900'}`} onClick={() => updateNumberFormats('')}>
                                <span>Any format</span>
                                {selectedNumberFormats.length === 0 && <span className="text-xs font-bold">Selected</span>}
                              </button>
                              {Object.entries(visibleNumberFormatGroups).map(([group, items]) => items.filter((item) => item !== 'Any format').length ? (
                                <div key={group} className="py-1">
                                  <p className="px-3 py-1 text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">{group}</p>
                                  {items.filter((item) => item !== 'Any format').map((item) => {
                                    const value = numberFormatValue(item)
                                    const checked = selectedNumberFormats.includes(value)
                                    return (
                                      <button key={item} type="button" className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm ${checked ? 'bg-purple-500/20 text-purple-100' : 'text-slate-200 hover:bg-slate-900'}`} onClick={() => updateNumberFormats(value)}>
                                        <span>{item}</span>
                                        <span className={`ml-3 h-4 w-4 rounded border ${checked ? 'border-purple-300 bg-purple-400' : 'border-slate-600'}`} />
                                      </button>
                                    )
                                  })}
                                </div>
                              ) : null)}
                            </div>
                          </div>
                        )}
                      </div>
                    </Field>
                    <Field label="Max price"><input className="input" value={form.price_max} onChange={(event) => updateField('price_max', event.target.value)} placeholder="40000" /></Field>
                    <Field label="Contains"><input className="input" value={form.contains} onChange={(event) => updateField('contains', event.target.value)} placeholder="77" /></Field>
                    <Field label="Starts with"><input className="input" value={form.starts_with} onChange={(event) => updateField('starts_with', event.target.value)} placeholder="12" /></Field>
                    <Field label="Ends with"><input className="input" value={form.ends_with} onChange={(event) => updateField('ends_with', event.target.value)} placeholder="00" /></Field>
                  </div>
                  <div className="mt-5 rounded-2xl bg-slate-900/70 p-4 text-sm">
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Rule Preview</p>
                    <p className="mt-2 text-slate-300">Number formats: <span className="font-bold text-white">{selectedNumberFormatLabels.length ? selectedNumberFormatLabels.join(', ') : 'Any format'}</span></p>
                  </div>
                  <div className="mt-6 space-y-4 border-t border-slate-800 pt-5">
                    <ToggleRow icon={Gauge} title="Immediate alerts mode" description="Scan frequently and send every newly released plate as soon as it appears on Xplate." checked={form.immediate_alerts_mode !== false} onChange={updateImmediateMode} />
                    <ToggleRow icon={Radio} title="Enable alert" description="Run this rule on the monitoring schedule." checked={form.enabled} onChange={(value) => updateField('enabled', value)} />
                    <div className="flex flex-wrap justify-end gap-3">
                      {editing && <button className="btn-muted" onClick={resetForm}>Cancel edit</button>}
                      <button className="btn-primary px-6" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : editing ? 'Save changes' : 'Create alert'}</button>
                    </div>
                  </div>
                </Card>
                {monitoringSpeedCard}
              </div>
              <div className="space-y-6">
                {savedRulesCard}
              </div>
            </div>
          )}

          {activeTab === 'Telegram Setup' && (
            <div className="space-y-6">
              {!telegramConfigured && (
                <div className="rounded-[24px] border border-amber-400/25 bg-amber-500/10 p-5 text-amber-100">
                  <h2 className="font-black">Telegram is not ready</h2>
                  <p className="mt-1 text-sm">Add Bot Token and Channel ID, then verify connection.</p>
                </div>
              )}
              <Card title="Telegram Settings" helper="These central credentials are used by Xplate alerts, verification, test sending, and Instagram sending." icon={MessageSquare}>
                <div className="grid gap-5 lg:grid-cols-2">
                  <Field label="Bot token"><input className="input" type="password" value={settings.telegram_bot_token || ''} onChange={(event) => updateSettingsField('telegram_bot_token', event.target.value.trim())} placeholder="Bot token" /></Field>
                  <Field label="Channel ID" helper="Use @channelusername or -100xxxxxxxxxx. The bot must be an admin."><input className="input" value={settings.telegram_chat_id || settings.telegram_channel_id || ''} onChange={(event) => updateSettingsField('telegram_chat_id', event.target.value)} onBlur={(event) => updateSettingsField('telegram_chat_id', normalizeTelegramChannel(event.target.value))} placeholder="@channelusername or -100..." /></Field>
                </div>
                <div className="mt-5 flex flex-wrap gap-3">
                  <button className="btn-primary" onClick={saveTelegramSettings}>Save Telegram settings</button>
                  <button className="btn-muted" onClick={verifyTelegramConnection} disabled={verifyingTelegram}>{verifyingTelegram ? 'Verifying...' : 'Verify Telegram connection'}</button>
                  <button className="btn-muted" onClick={handleTestChannelAlert} disabled={workingAction === 'test-channel'}>{workingAction === 'test-channel' ? 'Sending test...' : 'Test Channel Alert'}</button>
                  <button className="btn-muted" onClick={() => testTarget ? handleTestTelegram(testTarget) : setMessage('Create or select an alert before sending a test.')} disabled={workingAction === 'test'}>{workingAction === 'test' ? 'Sending rule test...' : 'Test Alert Rule'}</button>
                </div>
              </Card>
              <div className="grid gap-6 lg:grid-cols-2">
                <Card title="Setup Checklist" helper="Telegram-only readiness checks." icon={ShieldCheck}>
                  <div className="space-y-3 text-sm">
                    {[
                      ['Bot token saved', Boolean(settings.telegram_bot_token)],
                      ['Channel ID saved', Boolean(normalizedChannelPreview)],
                      ['Connection verified', telegramVerification?.ok === true],
                      ['Alert rule test available', Boolean(testTarget)],
                    ].map(([label, ok]) => (
                      <div key={label} className="flex items-center justify-between rounded-2xl bg-slate-900/70 p-3">
                        <span className="text-slate-300">{label}</span>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${ok ? 'bg-emerald-500/15 text-emerald-200' : 'bg-amber-500/15 text-amber-100'}`}>{ok ? 'Ready' : 'Needed'}</span>
                      </div>
                    ))}
                  </div>
                </Card>
                <Card title="Telegram Status" helper="Latest verification result and normalized channel." icon={Activity}>
                  <div className="space-y-3 text-sm">
                    <div className="rounded-2xl bg-slate-900/70 p-3"><span className="text-slate-500">Status</span><p className="mt-1 font-bold text-white">{telegramVerification?.message || (telegramConfigured ? 'Saved, not verified this session' : 'Missing credentials')}</p></div>
                    <div className="rounded-2xl bg-slate-900/70 p-3"><span className="text-slate-500">Channel</span><p className="mt-1 font-bold text-white">{normalizedChannelPreview || 'Not set'}</p></div>
                  </div>
                </Card>
              </div>
            </div>
          )}

          {activeTab === 'Instagram Setup' && (
            <div className="space-y-6">
              <div className={`rounded-[24px] border p-5 ${instagramProviderConfigured ? 'border-emerald-400/25 bg-emerald-500/10 text-emerald-100' : 'border-amber-400/25 bg-amber-500/10 text-amber-100'}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-black">{instagramProviderConfigured ? 'Instagram provider is configured.' : 'Instagram provider is not configured. Add API token and actor ID, then save settings.'}</h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 opacity-90">Instagram monitoring checks selected accounts for new plate posts and can send matching posts to Telegram.</p>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${statusBadge(instagramProviderConfigured ? 'Ready' : 'Warning')}`}>{instagramProviderConfigured ? 'Configured' : 'Needs setup'}</span>
                </div>
              </div>

              <div className={`rounded-[24px] border p-5 ${instagramSendingEnabled ? 'border-emerald-400/25 bg-emerald-500/10 text-emerald-100' : 'border-amber-400/25 bg-amber-500/10 text-amber-100'}`}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="font-black">{instagramStatusMessage}</h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 opacity-90">{instagramStatusDetail}</p>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${statusBadge(instagramSendingEnabled ? 'Ready' : 'Warning')}`}>{instagramSendingEnabled ? 'Enabled' : 'Paused'}</span>
                </div>
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                  <div className="rounded-2xl bg-slate-950/35 p-3"><span className="opacity-70">Accounts added</span><p className="mt-1 font-black text-white">{instagramAccounts.length}</p></div>
                  <div className="rounded-2xl bg-slate-950/35 p-3"><span className="opacity-70">Last baseline reset</span><p className="mt-1 font-black text-white">{instagramSettings.instagram_baseline_created_at || instagramSettings.last_baseline_reset_at || 'Never'}</p></div>
                  <div className="rounded-2xl bg-slate-950/35 p-3"><span className="opacity-70">Last Instagram scan</span><p className="mt-1 font-black text-white">{instagramSettings.last_instagram_scan_at || instagramSettings.last_checked_at || 'Never'}</p></div>
                  <div className="rounded-2xl bg-slate-950/35 p-3"><span className="opacity-70">Monitoring enabled</span><p className="mt-1 font-black text-white">{instagramSettings.enabled ? 'yes' : 'no'}</p></div>
                  <div className="rounded-2xl bg-slate-950/35 p-3"><span className="opacity-70">Auto-send enabled</span><p className="mt-1 font-black text-white">{instagramSettings.send_all_new_posts ? 'yes' : 'no'}</p></div>
                  <div className="rounded-2xl bg-slate-950/35 p-3"><span className="opacity-70">Telegram sending</span><p className="mt-1 font-black text-white">{telegramConfigured ? 'Ready' : 'Missing settings'}</p></div>
                </div>
              </div>

              <div className="grid items-start gap-6 2xl:grid-cols-[minmax(0,1.35fr)_minmax(24rem,0.65fr)]">
                <Card title="Instagram Monitoring" helper="Choose what gets watched and how posts are interpreted." icon={Image}>
                  <div className="space-y-4">
                    <InstagramSection title="Monitoring">
                      <ToggleRow icon={Radio} title="Enable Instagram monitoring" description="Check selected Instagram accounts for new plate posts." checked={instagramSettings.enabled} onChange={(value) => updateInstagramField('enabled', value)} />
                      <ToggleRow icon={Send} title="Send all new Instagram posts" description="Every new post after baseline can trigger Telegram." checked={instagramSettings.send_all_new_posts} onChange={(value) => updateInstagramField('send_all_new_posts', value)} />
                    </InstagramSection>
                    <InstagramSection title="Detection">
                      <ToggleRow icon={FileText} title="Extract plate numbers from captions" description="Best-effort detection of plate details." checked={instagramSettings.extract_plate_numbers} onChange={(value) => updateInstagramField('extract_plate_numbers', value)} />
                      <ToggleRow icon={Eye} title="Use OCR detection" description="Try to read plate numbers from images." checked={instagramSettings.extract_plate_details_from_images} onChange={(value) => updateInstagramField('extract_plate_details_from_images', value)} />
                    </InstagramSection>
                    <InstagramSection title="Telegram sending">
                      <ToggleRow icon={Image} title="Send Instagram image to Telegram" description="Use Telegram sendPhoto for post images." checked={instagramSettings.send_instagram_image_to_telegram} onChange={(value) => updateInstagramField('send_instagram_image_to_telegram', value)} />
                      <ToggleRow icon={MessageSquare} title="Include caption" description="Keep a shortened caption preview." checked={instagramSettings.include_caption} onChange={(value) => updateInstagramField('include_caption', value)} />
                      <ToggleRow icon={Image} title="Include post image" description="Store image URL for provider support." checked={instagramSettings.include_post_image} onChange={(value) => updateInstagramField('include_post_image', value)} />
                    </InstagramSection>
                  </div>

                  <div className="mt-8 space-y-5">
                    <Field label="Instagram accounts" helper="Add one username or profile URL per line.">
                      <textarea
                        className="input min-h-[180px] resize-y leading-6"
                        value={instagramAccountsText}
                        onChange={(event) => updateInstagramAccounts(event.target.value)}
                        placeholder={'raknumber\nplateselect\nexample_account\nhttps://www.instagram.com/example/'}
                      />
                    </Field>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-slate-400">{instagramAccounts.length} {instagramAccounts.length === 1 ? 'account' : 'accounts'} added</p>
                      <div className="flex flex-wrap gap-2">
                        <button className="btn-muted" onClick={clearInstagramAccounts}>Clear accounts</button>
                        <button className="btn-muted" onClick={removeDuplicateInstagramAccounts}>Remove duplicates</button>
                        <button className="btn-muted" onClick={sortInstagramAccounts}>Sort A-Z</button>
                      </div>
                    </div>
                    {instagramAccounts.length === 0 && <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-sm text-slate-400">No Instagram accounts added yet.</div>}
                    <div className="max-w-sm">
                      <Field label="Check interval in minutes" helper="Recommended: 10 minutes or more to avoid provider limits.">
                        <input className="input" type="number" min="1" value={instagramSettings.check_interval_minutes || 10} onChange={(event) => updateInstagramField('check_interval_minutes', Number(event.target.value || 10))} />
                      </Field>
                    </div>
                  </div>
                </Card>

                <Card title="Provider Settings" helper="Connect the provider used to fetch Instagram posts." icon={Settings2}>
                  <div className="space-y-5">
                    <div className="grid gap-4">
                      <Field label="Instagram provider"><select className="input" value={instagramSettings.instagram_provider || 'Apify'} onChange={(event) => updateInstagramField('instagram_provider', event.target.value)}><option>Apify</option><option>Custom API</option></select></Field>
                      {(instagramSettings.instagram_provider || 'Apify') === 'Apify' && <Field label="Apify API token"><input className="input" type="password" value={instagramSettings.apify_api_token || ''} onChange={(event) => updateInstagramField('apify_api_token', event.target.value.trim())} /></Field>}
                      {(instagramSettings.instagram_provider || 'Apify') === 'Apify' && <Field label="Apify actor ID" helper="Use apify/instagram-post-scraper or apify/instagram-scraper."><input className="input" value={instagramSettings.apify_actor_id || 'apify/instagram-post-scraper'} onChange={(event) => updateInstagramField('apify_actor_id', event.target.value.trim())} /></Field>}
                    </div>

                    {!instagramProviderConfigured && <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 p-4 text-sm font-semibold text-amber-100">{instagramProviderMissingReason}</div>}

                    <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-1">
                      <button className="btn-muted min-h-10 justify-center" onClick={verifyInstagramProvider} disabled={!instagramProviderConfigured || instagramWorking === 'verify-provider'}>{instagramWorking === 'verify-provider' ? 'Verifying...' : 'Verify Instagram provider'}</button>
                      <button className="btn-muted min-h-10 justify-center" onClick={() => runInstagramAction('run', api.runInstagramNow, 'Instagram check completed.')} disabled={!instagramProviderConfigured || instagramWorking === 'run'}><Play size={14} /> {instagramWorking === 'run' ? 'Running...' : 'Run Instagram check now'}</button>
                      <button className="btn-muted min-h-10 justify-center" onClick={() => runInstagramAction('baseline', api.resetInstagramBaseline, 'Instagram baseline reset. Future posts only.')} disabled={!instagramProviderConfigured || instagramWorking === 'baseline'}><RefreshCw size={14} /> {instagramWorking === 'baseline' ? 'Resetting...' : 'Reset Instagram baseline'}</button>
                      <button className="btn-muted min-h-10 justify-center" onClick={() => runInstagramAction('latest', api.sendLatestInstagram, 'Manual Instagram send.')} disabled={!instagramProviderConfigured || instagramWorking === 'latest'}><Send size={14} /> {instagramWorking === 'latest' ? 'Sending...' : 'Send latest post from all accounts'}</button>
                    </div>

                    <div className="grid gap-3 text-sm sm:grid-cols-2">
                      <div className="rounded-2xl bg-slate-900/70 p-3"><span className="text-slate-500">Provider connected</span><p className="mt-1 font-bold text-white">{(instagramProviderStatus?.provider_connected ?? instagramSettings.provider_connected) ? 'yes' : 'no'}</p></div>
                      <div className="rounded-2xl bg-slate-900/70 p-3"><span className="text-slate-500">Token found</span><p className="mt-1 font-bold text-white">{(instagramProviderStatus?.token_found ?? Boolean(instagramSettings.apify_api_token)) ? 'yes' : 'no'}</p></div>
                      <div className="rounded-2xl bg-slate-900/70 p-3"><span className="text-slate-500">Actor ID found</span><p className="mt-1 font-bold text-white">{(instagramProviderStatus?.actor_id_found ?? Boolean(instagramSettings.apify_actor_id)) ? 'yes' : 'no'}</p></div>
                      <div className="rounded-2xl bg-slate-900/70 p-3"><span className="text-slate-500">Last provider error</span><p className="mt-1 break-words font-bold text-white">{instagramProviderStatus?.last_provider_error || instagramSettings.last_provider_error || 'None'}</p></div>
                    </div>
                  </div>
                </Card>
              </div>

              <div className="sticky bottom-4 z-10 rounded-[24px] border border-slate-800 bg-slate-950/95 p-4 shadow-2xl shadow-black/30 backdrop-blur">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="text-sm">
                    <p className={`font-bold ${instagramDirty ? 'text-amber-100' : 'text-slate-200'}`}>{instagramDirty ? 'Unsaved Instagram changes' : 'Instagram settings are up to date'}</p>
                    <p className="mt-1 text-slate-500">{instagramLastSavedAt ? `Last saved at ${instagramLastSavedAt}` : 'No saved changes in this session'}</p>
                  </div>
                  <button className="btn-primary px-6" onClick={() => saveInstagramSettings()} disabled={instagramWorking === 'save'}>{instagramWorking === 'save' ? 'Saving...' : 'Save Instagram settings'}</button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'Monitoring & Logs' && (
            <div className="space-y-6">
              <Card title="Activity Log" helper="Readable alert events: matches, skips, sends, and Telegram errors." icon={Activity} action={<button className="btn-muted" onClick={() => setConfirmClearLogs(true)}>Clear logs</button>}>
                <div className="flex flex-wrap gap-2">
                  {logFilters.map((filter) => (
                    <button key={filter} className={`rounded-full px-3.5 py-2 text-sm ${logFilter === filter ? 'bg-purple-500 text-white' : 'bg-slate-900 text-slate-300 hover:bg-slate-800'}`} onClick={() => setLogFilter(filter)}>{filter}</button>
                  ))}
                </div>
                {confirmClearLogs && (
                  <div className="mt-4 rounded-2xl bg-rose-500/10 p-4 text-sm text-rose-100">
                    <p>Confirm clearing all alert logs. This cannot be undone.</p>
                    <div className="mt-3 flex gap-2"><button className="btn-danger" onClick={confirmClearLogsHandler}>Confirm clear</button><button className="btn-muted" onClick={() => setConfirmClearLogs(false)}>Cancel</button></div>
                  </div>
                )}
                <div className="mt-5 space-y-3">
                  {preparedLogs.length === 0 ? (
                    <div className="rounded-2xl bg-slate-900/70 p-5 text-slate-400">No activity yet. Run a check or create an alert to start monitoring.</div>
                  ) : preparedLogs.map((log) => {
                    const severity = String(log.severity || log.status || '').toLowerCase()
                    const Icon = severity.includes('error') ? XCircle : severity.includes('success') ? CheckCircle2 : AlertTriangle
                    return (
                      <div key={log.id} className="rounded-2xl bg-slate-900/70 p-4">
                        <button className="flex w-full flex-wrap items-start justify-between gap-4 text-left" onClick={() => showLogDetails(log)}>
                          <div className="flex min-w-0 gap-3">
                            <span className={`rounded-xl p-2 ${severity.includes('error') ? 'bg-rose-500/10 text-rose-200' : severity.includes('success') ? 'bg-emerald-500/10 text-emerald-200' : 'bg-amber-500/10 text-amber-200'}`}><Icon size={17} /></span>
                            <span className="min-w-0">
                              <span className="block text-xs text-slate-500">{log.checked_at}</span>
                              <span className="mt-1 block font-bold text-white">{log.event_type || titleCase(log.status) || 'Alert event'} - {log.alert_name}</span>
                              <span className="mt-1 block break-words text-sm text-slate-400">{log.message}</span>
                            </span>
                          </div>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${statusBadge(log.status)}`}>{log.status || 'log'}</span>
                        </button>
                        {expandedLog === log.id && (
                          <div className="mt-4 rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-300">
                            <p><b>Reason:</b> {log.reason || 'Not available'}</p>
                            {log.error && <p className="mt-2 text-rose-200"><b>Telegram/API error:</b> {log.error}</p>}
                            {!!log.details?.length && <ul className="mt-3 list-disc space-y-1 pl-5">{log.details.map((item, index) => <li key={index}>{item}</li>)}</ul>}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </Card>
            </div>
          )}
        </main>
        <DetailPanel listing={selectedListing} log={selectedLog} />
      </div>
    </div>
  )
}
