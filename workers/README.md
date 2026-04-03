# Risk Space Workers

Cloudflare Workers for the Risk Space MCP API and LINE Bot.

## Architecture

```
LINE App
  │
  ▼
┌──────────────────────┐     ┌─────────────────────────┐
│  risk-space-line-bot │────▶│   risk-space-mcp        │
│  (Cloudflare Worker) │     │   (Cloudflare Worker)   │
│                      │     │                         │
│  LINE webhook        │     │  GET /mcp/get_risk_field│
│  KV: LINE_KV         │     │  GET /mcp/get_hotspots  │
└──────────────────────┘     │  GET /mcp/get_signals   │
                             │  POST /mcp/update_field │
                             │  GET /health            │
                             │                         │
                             │  R2: grid_risk.json     │
                             │  KV: RISK_KV (cache)    │
                             └─────────────────────────┘
```

## Prerequisites

1. **Cloudflare account** with Workers (free plan works)
2. **wrangler CLI** installed and authenticated:
   ```bash
   npm install -g wrangler
   wrangler login
   ```
3. **LINE Developers account** with a Messaging API channel:
   - https://developers.line.biz/console/
   - Create a new Provider and Channel (Messaging API)
   - Note the **Channel secret** and **Channel access token** (long-lived)

## Setup

### 1. One-command deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

This script will:
- Create R2 bucket `risk-space-data`
- Create KV namespaces `RISK_KV` and `LINE_KV`
- Upload `grid_risk.json` from `dashboard/data/` to R2
- Deploy both Workers
- Prompt for LINE secrets

### 2. Manual setup

If you prefer step-by-step:

```bash
# Create R2 bucket
wrangler r2 bucket create risk-space-data

# Create KV namespaces
wrangler kv namespace create RISK_KV
wrangler kv namespace create LINE_KV

# Update wrangler.toml files with the KV namespace IDs from above output

# Upload data to R2
wrangler r2 object put risk-space-data/grid_risk.json \
  --file ../dashboard/data/grid_risk.json \
  --content-type "application/json"

# Deploy MCP worker
cd risk-space-mcp
npm install
wrangler deploy

# Deploy LINE bot worker
cd ../line-bot
npm install
wrangler secret put LINE_CHANNEL_SECRET
wrangler secret put LINE_CHANNEL_ACCESS_TOKEN
wrangler deploy
```

### 3. Configure LINE webhook

1. Go to LINE Developers Console
2. Select your Messaging API channel
3. Under **Messaging API** tab:
   - Set **Webhook URL** to: `https://risk-space-line-bot.<your-subdomain>.workers.dev/webhook`
   - Enable **Use webhook**
   - Disable **Auto-reply messages** (optional, recommended)

### 4. Update MCP base URL

Edit `line-bot/wrangler.toml` and set `MCP_BASE_URL` to the actual deployed URL:

```toml
[vars]
MCP_BASE_URL = "https://risk-space-mcp.<your-subdomain>.workers.dev"
```

Then redeploy:
```bash
cd line-bot && wrangler deploy
```

## Testing

### MCP API

```bash
# Health check
curl https://risk-space-mcp.<your-subdomain>.workers.dev/health

# Risk field query (Shinjuku area)
curl "https://risk-space-mcp.<your-subdomain>.workers.dev/mcp/get_risk_field?lat=35.69&lon=139.70&radius_km=2"

# Hotspots
curl "https://risk-space-mcp.<your-subdomain>.workers.dev/mcp/get_hotspots?layer=crime&limit=5"

# Signals
curl "https://risk-space-mcp.<your-subdomain>.workers.dev/mcp/get_signals"

# Submit a report
curl -X POST "https://risk-space-mcp.<your-subdomain>.workers.dev/mcp/update_field" \
  -H "Content-Type: application/json" \
  -d '{"lat":35.69,"lon":139.70,"layer":"crime","subtype":"suspicious_person","severity":3,"description":"Test report"}'
```

### LINE Bot

Send these messages in LINE to test each handler:
- **Location message** (tap + button, choose Location)
- **"今から帰る"** — start trip
- **"ついた"** — confirm arrival
- **"不審者"** — danger report
- **"ホットスポット"** — top risk areas
- **"パトロール"** — patrol recommendations
- **Any other text** — help menu

## Environment Variables and Secrets

### risk-space-mcp

| Binding   | Type | Description                |
|-----------|------|----------------------------|
| RISK_R2   | R2   | `risk-space-data` bucket   |
| RISK_KV   | KV   | Cache and signals storage  |

### line-bot

| Binding/Secret              | Type   | Description                        |
|-----------------------------|--------|------------------------------------|
| LINE_KV                     | KV     | User state (trips, locations)      |
| MCP_BASE_URL                | Var    | MCP worker URL                     |
| LINE_CHANNEL_SECRET         | Secret | LINE channel secret (HMAC verify)  |
| LINE_CHANNEL_ACCESS_TOKEN   | Secret | LINE channel access token (reply)  |

## Local Development

```bash
# MCP worker (port 8787)
cd risk-space-mcp
wrangler dev

# LINE bot (port 8788)
cd line-bot
wrangler dev --port 8788
```

For LINE webhook testing locally, use ngrok or cloudflared tunnel:
```bash
npx ngrok http 8788
# Then set the ngrok URL as webhook URL in LINE Developers Console
```
