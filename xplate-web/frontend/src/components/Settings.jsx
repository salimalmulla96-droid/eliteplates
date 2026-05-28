export default function Settings({ settings, setSettings, saveSettings, clearHistory, clearFavorites }) {
  const update = (key, value) => setSettings((current) => ({ ...current, [key]: value }))
  const normalizeTelegramChannel = (value) => {
    let text = String(value || '').trim()
    text = text.replace(/^https?:\/\/t\.me\//i, '').replace(/^t\.me\//i, '').replace(/\/+$/, '')
    if (text && !text.startsWith('@') && !text.startsWith('-100') && !/^-?\d+$/.test(text)) text = `@${text}`
    return text
  }
  const handleSave = async () => {
    const normalized = {
      ...settings,
      telegram_chat_id: normalizeTelegramChannel(settings.telegram_chat_id || ''),
    }
    const response = await saveSettings(normalized)
    if (response?.settings) setSettings(response.settings)
  }
  return (
    <section className="glass max-w-3xl rounded-3xl p-6">
      <h1 className="text-3xl font-black">Settings</h1>
      <p className="mt-2 text-slate-400">Control theme, defaults, and local data.</p>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <select className="input" value={settings.theme || 'dark'} onChange={(e) => update('theme', e.target.value)}><option>dark</option><option>light</option></select>
        <select className="input" value={settings.accent || 'purple'} onChange={(e) => update('accent', e.target.value)}><option>blue</option><option>purple</option><option>green</option><option>red</option></select>
        <select className="input" value={settings.default_search_depth || 'All pages'} onChange={(e) => update('default_search_depth', e.target.value)}><option>All pages</option><option>First 10 pages</option><option>First 5 pages</option><option>First page only</option></select>
        <select className="input" value={settings.table_density || 'comfortable'} onChange={(e) => update('table_density', e.target.value)}><option>comfortable</option><option>compact</option></select>
        <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.save_history !== false} onChange={(e) => update('save_history', e.target.checked)} />Save search history</label>
        <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.show_seller_details !== false} onChange={(e) => update('show_seller_details', e.target.checked)} />Show seller details panel</label>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <label className="flex flex-col gap-2 text-sm text-slate-300">
          <span>Global Telegram bot token</span>
          <input className="input" type="password" value={settings.telegram_bot_token || ''} onChange={(e) => update('telegram_bot_token', e.target.value.trim())} placeholder="Bot token" />
        </label>
        <label className="flex flex-col gap-2 text-sm text-slate-300">
          <span>Global Telegram channel ID</span>
          <input className="input" value={settings.telegram_chat_id || ''} onChange={(e) => update('telegram_chat_id', e.target.value)} onBlur={(e) => update('telegram_chat_id', normalizeTelegramChannel(e.target.value))} placeholder="@channelusername or -100xxxxxxxxxx" />
          <p className="text-xs text-slate-500">Use your channel username like @mychannel or channel ID like -100xxxxxxxxxx. The bot must be admin in the channel.</p>
        </label>
      </div>
      <div className="mt-6 rounded-3xl border border-line bg-slate-950/50 p-5">
        <h2 className="text-lg font-bold">Default Telegram Message Preferences</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm text-slate-300">
            <span>Message title</span>
            <input className="input" value={settings.telegram_message_title || 'New Plate Alert'} onChange={(e) => update('telegram_message_title', e.target.value)} placeholder="Xplate Scout Alert" />
          </label>
          <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.telegram_compact_mode === true} onChange={(e) => update('telegram_compact_mode', e.target.checked)} />Compact message</label>
          <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.telegram_emojis !== false} onChange={(e) => update('telegram_emojis', e.target.checked)} />Emojis on</label>
          <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.telegram_include_seller_details !== false} onChange={(e) => update('telegram_include_seller_details', e.target.checked)} />Include seller details</label>
          <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.telegram_include_detected_time !== false} onChange={(e) => update('telegram_include_detected_time', e.target.checked)} />Include detected time</label>
          <label className="flex gap-2 text-sm text-slate-300"><input type="checkbox" checked={settings.telegram_include_match_reason !== false} onChange={(e) => update('telegram_include_match_reason', e.target.checked)} />Include match reason</label>
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">Per-alert Telegram credentials override global settings when set. Leave alert Telegram fields blank to use global defaults.</p>
      <div className="mt-6 flex gap-3">
        <button className="btn-primary" onClick={handleSave}>Save settings</button>
        <button className="btn-muted" onClick={clearHistory}>Clear history</button>
        <button className="btn-muted" onClick={clearFavorites}>Clear favorites</button>
      </div>
    </section>
  )
}
