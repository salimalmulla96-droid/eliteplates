# Railway backend variables

For normal saved-rule alerts and Telegram connection tests, add these variables
under **Railway → Backend service → Variables**:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

The backend also continues to support credentials saved through the Xplate
Settings page. Rule-specific credentials take precedence, followed by Railway
environment variables, then saved settings.

To pin each daily saved-rule Excel document after Telegram accepts it, add this
variable to the Railway **backend service**:

```env
TELEGRAM_PIN_DAILY_REPORTS=true
```

If the variable is missing or set to `false`, reports are sent normally and are
not pinned.

The report uses the same Telegram bot token and destination chat/channel as the
saved alert rule. The bot must be an administrator in that destination with
permission to post and pin messages. A pin failure is logged as a warning and
does not change a successful report delivery into a failure.
