/**
 * Risk Space MCP — Cloudflare Workers endpoint
 *
 * Provides a spatial risk-field API backed by R2 (grid_risk.json) and KV
 * (realtime signals, user reports, cache).
 *
 * Endpoints:
 *   GET  /mcp/get_risk_field   — risk score for lat/lon + radius
 *   GET  /mcp/get_hotspots     — top-N cells by risk_score
 *   GET  /mcp/get_signals      — realtime signals from KV
 *   POST /mcp/update_field     — accept user reports
 *   GET  /health               — health check
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const EARTH_RADIUS_KM = 6371;

/** Haversine distance in km between two points (degrees). */
function haversine(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Return a standard JSON response. */
function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      ...headers,
    },
  });
}

/** Parse a URL's search params with defaults. */
function params(url, defaults = {}) {
  const out = { ...defaults };
  for (const [k, v] of url.searchParams.entries()) {
    if (k in defaults) {
      const type = typeof defaults[k];
      if (type === "number") out[k] = Number(v);
      else out[k] = v;
    } else {
      out[k] = v;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Grid loader (from R2, cached in KV for 5 min)
// ---------------------------------------------------------------------------

const GRID_CACHE_KEY = "cache:grid_risk";
const GRID_CACHE_TTL = 300; // seconds

async function loadGrid(env) {
  // 1. Try KV cache
  const cached = await env.RISK_KV.get(GRID_CACHE_KEY, { type: "json" });
  if (cached) return cached;

  // 2. Load from R2
  const obj = await env.RISK_R2.get("grid_risk.json");
  if (!obj) throw new Error("grid_risk.json not found in R2");

  const text = await obj.text();
  const grid = JSON.parse(text);

  // 3. Store in KV (fire-and-forget, TTL in seconds)
  await env.RISK_KV.put(GRID_CACHE_KEY, text, { expirationTtl: GRID_CACHE_TTL });

  return grid;
}

// ---------------------------------------------------------------------------
// Prefecture lookup (simple centroid-based — grid cells don't carry prefecture)
// ---------------------------------------------------------------------------

const PREFECTURE_BOUNDS = {
  "01": { name: "北海道", latMin: 41.3, latMax: 45.6, lonMin: 139.3, lonMax: 145.8 },
  "13": { name: "東京都", latMin: 35.5, latMax: 35.9, lonMin: 138.9, lonMax: 139.9 },
  "14": { name: "神奈川県", latMin: 35.1, latMax: 35.7, lonMin: 138.9, lonMax: 139.8 },
  "23": { name: "愛知県", latMin: 34.5, latMax: 35.4, lonMin: 136.7, lonMax: 137.7 },
  "27": { name: "大阪府", latMin: 34.2, latMax: 35.0, lonMin: 135.0, lonMax: 135.8 },
  "40": { name: "福岡県", latMin: 33.0, latMax: 33.9, lonMin: 130.0, lonMax: 131.2 },
};

// ---------------------------------------------------------------------------
// Endpoint handlers
// ---------------------------------------------------------------------------

/**
 * GET /mcp/get_risk_field?lat=X&lon=X&radius_km=X&layers=crime,traffic,disaster
 */
async function handleGetRiskField(url, env) {
  const { lat, lon, radius_km, layers } = params(url, {
    lat: 0,
    lon: 0,
    radius_km: 1,
    layers: "crime,traffic,disaster,weather",
  });

  if (lat === 0 && lon === 0) {
    return json({ error: "lat and lon are required" }, 400);
  }

  const allowedLayers = new Set(layers.split(",").map((s) => s.trim()));
  const grid = await loadGrid(env);

  // Find cells within radius
  const matched = [];
  for (const cell of grid) {
    const dist = haversine(lat, lon, cell.lat, cell.lon);
    if (dist <= radius_km) {
      matched.push({ ...cell, distance_km: Math.round(dist * 1000) / 1000 });
    }
  }

  if (matched.length === 0) {
    return json({
      lat,
      lon,
      radius_km,
      cells_found: 0,
      risk_score: 0,
      breakdown: {},
      message: "No grid cells found within radius. Try a larger radius.",
    });
  }

  // Compute weighted risk score (inverse-distance weighting)
  let weightSum = 0;
  let weightedScore = 0;
  const layerCounts = {};
  const layerScores = {};

  for (const cell of matched) {
    const w = cell.distance_km < 0.01 ? 1000 : 1 / cell.distance_km;
    weightSum += w;
    weightedScore += cell.risk_score * w;

    // Breakdown by layer
    for (const [layer, count] of Object.entries(cell.layers || {})) {
      if (!allowedLayers.has(layer)) continue;
      layerCounts[layer] = (layerCounts[layer] || 0) + count;
      layerScores[layer] = (layerScores[layer] || 0) + cell.risk_score * w * (count / cell.count);
    }
  }

  const compositeScore = Math.round((weightedScore / weightSum) * 10000) / 10000;

  // Normalise layer scores
  const breakdown = {};
  for (const layer of Object.keys(layerCounts)) {
    breakdown[layer] = {
      event_count: layerCounts[layer],
      weighted_score: Math.round((layerScores[layer] / weightSum) * 10000) / 10000,
    };
  }

  // Top subtypes across matched cells
  const subtypeTotals = {};
  for (const cell of matched) {
    for (const [st, cnt] of Object.entries(cell.subtypes || {})) {
      subtypeTotals[st] = (subtypeTotals[st] || 0) + cnt;
    }
  }
  const topSubtypes = Object.entries(subtypeTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([subtype, count]) => ({ subtype, count }));

  return json({
    lat,
    lon,
    radius_km,
    cells_found: matched.length,
    risk_score: compositeScore,
    risk_level: compositeScore >= 0.8 ? "high" : compositeScore >= 0.4 ? "medium" : "low",
    breakdown,
    top_subtypes: topSubtypes,
    cached: false,
  });
}

/**
 * GET /mcp/get_hotspots?layer=all&limit=20&prefecture=X
 */
async function handleGetHotspots(url, env) {
  const { layer, limit, prefecture } = params(url, {
    layer: "all",
    limit: 20,
    prefecture: "",
  });

  const grid = await loadGrid(env);
  let filtered = grid;

  // Filter by layer
  if (layer !== "all") {
    filtered = filtered.filter((c) => c.layers && c.layers[layer] > 0);
  }

  // Filter by prefecture (rough bounding-box match)
  if (prefecture) {
    const prefLower = prefecture.toLowerCase();
    const bounds = Object.values(PREFECTURE_BOUNDS).find(
      (b) => b.name === prefecture || b.name.includes(prefecture)
    );
    if (bounds) {
      filtered = filtered.filter(
        (c) =>
          c.lat >= bounds.latMin &&
          c.lat <= bounds.latMax &&
          c.lon >= bounds.lonMin &&
          c.lon <= bounds.lonMax
      );
    }
  }

  // Sort by risk_score descending
  filtered.sort((a, b) => b.risk_score - a.risk_score);
  const topN = filtered.slice(0, Math.min(limit, 100));

  return json({
    layer,
    prefecture: prefecture || "all",
    total_candidates: filtered.length,
    returned: topN.length,
    hotspots: topN.map((c) => ({
      lat: c.lat,
      lon: c.lon,
      risk_score: c.risk_score,
      event_count: c.count,
      avg_severity: c.avg_severity,
      layers: c.layers,
      dominant_subtype: Object.entries(c.subtypes || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || null,
    })),
  });
}

/**
 * GET /mcp/get_signals
 * Return realtime signals stored in KV under prefix "signal:"
 */
async function handleGetSignals(url, env) {
  const { limit } = params(url, { limit: 50 });

  const list = await env.RISK_KV.list({ prefix: "signal:", limit: Math.min(limit, 200) });
  const signals = [];

  for (const key of list.keys) {
    const val = await env.RISK_KV.get(key.name, { type: "json" });
    if (val) signals.push(val);
  }

  // Sort by timestamp descending
  signals.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));

  return json({
    count: signals.length,
    signals,
  });
}

/**
 * POST /mcp/update_field
 * Accept user reports and store in KV.
 *
 * Body: { lat, lon, layer, subtype, severity, description, reporter_id }
 */
async function handleUpdateField(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  const { lat, lon, layer, subtype, severity, description, reporter_id } = body;

  if (!lat || !lon || !layer) {
    return json({ error: "lat, lon, and layer are required" }, 400);
  }

  const validLayers = new Set(["crime", "traffic", "disaster", "weather"]);
  if (!validLayers.has(layer)) {
    return json({ error: `Invalid layer: ${layer}. Must be one of: ${[...validLayers].join(", ")}` }, 400);
  }

  if (severity !== undefined && (severity < 1 || severity > 5)) {
    return json({ error: "severity must be 1-5" }, 400);
  }

  const id = crypto.randomUUID();
  const timestamp = new Date().toISOString();

  const report = {
    id,
    layer,
    subtype: subtype || "user_report",
    geometry: { type: "Point", coordinates: [lon, lat] },
    lat,
    lon,
    severity: severity || 2,
    description: description || "",
    reporter_id: reporter_id || "anonymous",
    timestamp,
    source: "user_report",
  };

  // Store as a signal (expires in 24h)
  await env.RISK_KV.put(`signal:${id}`, JSON.stringify(report), {
    expirationTtl: 86400,
  });

  // Also store in a user-report list (expires in 7 days)
  await env.RISK_KV.put(`report:${id}`, JSON.stringify(report), {
    expirationTtl: 604800,
  });

  return json({ ok: true, id, timestamp }, 201);
}

/**
 * GET /health
 */
async function handleHealth(env) {
  // Quick R2 + KV connectivity check
  let r2ok = false;
  let kvok = false;

  try {
    const head = await env.RISK_R2.head("grid_risk.json");
    r2ok = head !== null;
  } catch {
    // R2 unavailable
  }

  try {
    await env.RISK_KV.put("health:ping", Date.now().toString(), { expirationTtl: 60 });
    const v = await env.RISK_KV.get("health:ping");
    kvok = v !== null;
  } catch {
    // KV unavailable
  }

  const status = r2ok && kvok ? "healthy" : "degraded";
  return json({ status, r2: r2ok, kv: kvok, timestamp: new Date().toISOString() }, r2ok && kvok ? 200 : 503);
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const { pathname } = url;
    const method = request.method;

    // CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    try {
      if (method === "GET" && pathname === "/mcp/get_risk_field") {
        return await handleGetRiskField(url, env);
      }
      if (method === "GET" && pathname === "/mcp/get_hotspots") {
        return await handleGetHotspots(url, env);
      }
      if (method === "GET" && pathname === "/mcp/get_signals") {
        return await handleGetSignals(url, env);
      }
      if (method === "POST" && pathname === "/mcp/update_field") {
        return await handleUpdateField(request, env);
      }
      if (method === "GET" && pathname === "/health") {
        return await handleHealth(env);
      }

      // Root — return API info
      if (method === "GET" && pathname === "/") {
        return json({
          name: "Risk Space MCP",
          version: "1.0.0",
          endpoints: [
            "GET  /mcp/get_risk_field?lat=X&lon=X&radius_km=X&layers=crime,traffic",
            "GET  /mcp/get_hotspots?layer=all&limit=20&prefecture=X",
            "GET  /mcp/get_signals",
            "POST /mcp/update_field",
            "GET  /health",
          ],
        });
      }

      return json({ error: "Not found" }, 404);
    } catch (err) {
      console.error("Unhandled error:", err);
      return json({ error: "Internal server error", detail: err.message }, 500);
    }
  },
};
