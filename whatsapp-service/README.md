# RaccBuddy WhatsApp Service 🦝

Node.js bridge that connects WhatsApp (via whatsapp-web.js) to the RaccBuddy Python core.

## Quick Start

```bash
# 1. Make sure the Python core is running on port 8000
# 2. Install dependencies
cd whatsapp-service
npm install

# 3. Start the service
npm start
```

On first run a **QR code** will appear in the terminal — scan it with WhatsApp (Linked Devices). Session is saved locally so you only scan once.

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable          | Default                  | Description                     |
|-------------------|--------------------------|---------------------------------|
| `PORT`            | `3001`                   | Health-check server port        |
| `PYTHON_CORE_URL` | `http://localhost:8000`  | Python core REST API base URL   |

## Docker

```bash
docker build -t raccbuddy-whatsapp .
docker run -it --rm \
  --network host \
  -v raccbuddy-wa-session:/app/.wwebjs_auth \
  raccbuddy-whatsapp
```

## Health Check

```bash
curl http://localhost:3001/health
```

## How It Works

1. `whatsapp-web.js` connects to WhatsApp via a headless Chromium browser.
2. Every incoming message (individual or group) is captured.
3. The message payload is POSTed to `http://<PYTHON_CORE_URL>/api/messages`.
4. The Python core processes it through the same pipeline as Telegram messages.
