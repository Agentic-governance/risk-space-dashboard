#!/usr/bin/env bash
#
# deploy.sh — Create R2 bucket, KV namespaces, upload data, deploy both Workers
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Prerequisites:
#   - wrangler CLI installed and authenticated (`wrangler login`)
#   - LINE secrets ready (channel secret + access token)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "  Risk Space Workers — Deploy Script"
echo "============================================"
echo ""

# ------------------------------------------------------------------
# 1. Create R2 bucket
# ------------------------------------------------------------------
echo "[1/6] Creating R2 bucket: risk-space-data ..."
if wrangler r2 bucket list 2>/dev/null | grep -q "risk-space-data"; then
  echo "  -> Already exists, skipping."
else
  wrangler r2 bucket create risk-space-data
  echo "  -> Created."
fi
echo ""

# ------------------------------------------------------------------
# 2. Create KV namespaces
# ------------------------------------------------------------------
echo "[2/6] Creating KV namespaces ..."

# RISK_KV (for MCP worker)
RISK_KV_ID=""
if wrangler kv namespace list 2>/dev/null | grep -q '"title": "risk-space-mcp-RISK_KV"'; then
  echo "  -> RISK_KV already exists."
  RISK_KV_ID=$(wrangler kv namespace list 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ns in data:
    if ns.get('title') == 'risk-space-mcp-RISK_KV':
        print(ns['id'])
        break
")
else
  echo "  -> Creating RISK_KV ..."
  RISK_KV_OUTPUT=$(wrangler kv namespace create RISK_KV --preview false 2>&1)
  echo "$RISK_KV_OUTPUT"
  RISK_KV_ID=$(echo "$RISK_KV_OUTPUT" | grep -oP 'id = "\K[^"]+' || echo "")
fi

# LINE_KV (for LINE bot worker)
LINE_KV_ID=""
if wrangler kv namespace list 2>/dev/null | grep -q '"title": "risk-space-line-bot-LINE_KV"'; then
  echo "  -> LINE_KV already exists."
  LINE_KV_ID=$(wrangler kv namespace list 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ns in data:
    if ns.get('title') == 'risk-space-line-bot-LINE_KV':
        print(ns['id'])
        break
")
else
  echo "  -> Creating LINE_KV ..."
  LINE_KV_OUTPUT=$(wrangler kv namespace create LINE_KV --preview false 2>&1)
  echo "$LINE_KV_OUTPUT"
  LINE_KV_ID=$(echo "$LINE_KV_OUTPUT" | grep -oP 'id = "\K[^"]+' || echo "")
fi

echo ""

# ------------------------------------------------------------------
# 3. Update wrangler.toml KV IDs
# ------------------------------------------------------------------
echo "[3/6] Updating wrangler.toml with KV namespace IDs ..."

if [ -n "$RISK_KV_ID" ]; then
  sed -i.bak "s/REPLACE_WITH_KV_NAMESPACE_ID/$RISK_KV_ID/" "$SCRIPT_DIR/risk-space-mcp/wrangler.toml"
  echo "  -> risk-space-mcp/wrangler.toml updated with RISK_KV_ID=$RISK_KV_ID"
fi

if [ -n "$LINE_KV_ID" ]; then
  sed -i.bak "s/REPLACE_WITH_KV_NAMESPACE_ID/$LINE_KV_ID/" "$SCRIPT_DIR/line-bot/wrangler.toml"
  echo "  -> line-bot/wrangler.toml updated with LINE_KV_ID=$LINE_KV_ID"
fi

# Clean up backup files
rm -f "$SCRIPT_DIR/risk-space-mcp/wrangler.toml.bak" "$SCRIPT_DIR/line-bot/wrangler.toml.bak"
echo ""

# ------------------------------------------------------------------
# 4. Upload data to R2
# ------------------------------------------------------------------
echo "[4/6] Uploading data to R2 ..."

# Upload grid_risk.json
GRID_FILE="$PROJECT_ROOT/dashboard/data/grid_risk.json"
if [ -f "$GRID_FILE" ]; then
  echo "  -> Uploading grid_risk.json ..."
  wrangler r2 object put risk-space-data/grid_risk.json --file "$GRID_FILE" --content-type "application/json"
else
  echo "  !! grid_risk.json not found at $GRID_FILE"
  echo "  !! Run the grid computation script first."
fi

# Upload hotspots
HOTSPOTS_FILE="$PROJECT_ROOT/data/normalized/hotspots_v2.json"
if [ -f "$HOTSPOTS_FILE" ]; then
  echo "  -> Uploading hotspots_v2.json ..."
  wrangler r2 object put risk-space-data/hotspots_v2.json --file "$HOTSPOTS_FILE" --content-type "application/json"
fi

# Upload events summary
SUMMARY_FILE="$PROJECT_ROOT/dashboard/data/summary.json"
if [ -f "$SUMMARY_FILE" ]; then
  echo "  -> Uploading summary.json ..."
  wrangler r2 object put risk-space-data/summary.json --file "$SUMMARY_FILE" --content-type "application/json"
fi

echo ""

# ------------------------------------------------------------------
# 5. Deploy Risk Space MCP worker
# ------------------------------------------------------------------
echo "[5/6] Deploying risk-space-mcp worker ..."
cd "$SCRIPT_DIR/risk-space-mcp"
npm install
wrangler deploy
echo ""

# ------------------------------------------------------------------
# 6. Deploy LINE bot worker
# ------------------------------------------------------------------
echo "[6/6] Deploying risk-space-line-bot worker ..."
cd "$SCRIPT_DIR/line-bot"
npm install

# Set LINE secrets (interactive prompts)
echo ""
echo "  Setting LINE secrets (you will be prompted for each value):"
echo ""

if [ -z "${LINE_CHANNEL_SECRET:-}" ]; then
  echo "  Enter LINE_CHANNEL_SECRET:"
  wrangler secret put LINE_CHANNEL_SECRET
else
  echo "$LINE_CHANNEL_SECRET" | wrangler secret put LINE_CHANNEL_SECRET
fi

if [ -z "${LINE_CHANNEL_ACCESS_TOKEN:-}" ]; then
  echo "  Enter LINE_CHANNEL_ACCESS_TOKEN:"
  wrangler secret put LINE_CHANNEL_ACCESS_TOKEN
else
  echo "$LINE_CHANNEL_ACCESS_TOKEN" | wrangler secret put LINE_CHANNEL_ACCESS_TOKEN
fi

wrangler deploy

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "============================================"
echo ""
echo "MCP endpoint:  https://risk-space-mcp.<your-subdomain>.workers.dev"
echo "LINE webhook:  https://risk-space-line-bot.<your-subdomain>.workers.dev/webhook"
echo ""
echo "Next steps:"
echo "  1. Update line-bot/wrangler.toml MCP_BASE_URL with the actual MCP URL"
echo "  2. In LINE Developers Console, set webhook URL to:"
echo "     https://risk-space-line-bot.<your-subdomain>.workers.dev/webhook"
echo "  3. Enable 'Use webhook' in LINE Developers Console"
echo "  4. Test: curl https://risk-space-mcp.<your-subdomain>.workers.dev/health"
echo ""
