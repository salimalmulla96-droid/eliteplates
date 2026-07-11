# Render Backend Deployment

The FastAPI application entry point is:

```text
app/main.py
```

The FastAPI variable is:

```python
app = FastAPI(title="Xplate Scout API")
```

## Render service settings

Root Directory:

```text
xplate-web/backend
```

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Do not use `--reload` on Render, and do not hardcode port `8000`. Render injects the correct `$PORT`.

## Required environment variables

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TZ=Asia/Dubai
TELEGRAM_PIN_DAILY_REPORTS=true
FRONTEND_URL=
```

`FRONTEND_URL` should be the deployed frontend origin, for example `https://your-frontend.vercel.app`. Multiple origins can be provided as a comma-separated list.

Local frontend origins are already allowed by the backend:

```text
http://localhost:5173
http://127.0.0.1:5173
http://localhost:5174
http://127.0.0.1:5174
```

Do not hardcode Telegram secrets in source files. Set them in Render environment variables or through the app settings UI.

## Startup checks

After a successful deploy, backend logs should include lines like:

```text
Xplate backend started
Telegram configuration loaded: yes
Xplate alert monitor scheduler started
```

The alert monitor, Instagram monitor, daily Excel reports, Telegram Excel sending, and Telegram pinning are started from the backend FastAPI process.

## Test URLs

After redeploying, test:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
https://YOUR-RENDER-SERVICE.onrender.com/api/health
https://YOUR-RENDER-SERVICE.onrender.com/docs
```

For local testing from this folder:

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```
