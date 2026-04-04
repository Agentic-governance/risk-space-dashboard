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
 *   GET  /mcp/get_weather      — weather forecast multipliers by prefecture + hour
 *   GET  /mcp/get_events       — holiday/event multipliers by prefecture + date
 *   GET  /mcp/get_dynamic_risk — combined risk (field + weather + events + temporal)
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
// Weather loader (from R2, cached in KV for 1 hour)
// ---------------------------------------------------------------------------

const WEATHER_CACHE_KEY = "cache:forecasts_all";
const WEATHER_CACHE_TTL = 3600; // 1 hour

async function loadWeather(env) {
  const cached = await env.RISK_KV.get(WEATHER_CACHE_KEY, { type: "json" });
  if (cached) return cached;

  const obj = await env.RISK_R2.get("forecasts_all.json");
  if (!obj) return null;

  const text = await obj.text();
  const data = JSON.parse(text);
  await env.RISK_KV.put(WEATHER_CACHE_KEY, text, { expirationTtl: WEATHER_CACHE_TTL });
  return data;
}

// ---------------------------------------------------------------------------
// Events loader (from R2, cached in KV for 1 hour)
// ---------------------------------------------------------------------------

const EVENTS_CACHE_KEY = "cache:all_events";
const EVENTS_CACHE_TTL = 3600; // 1 hour

async function loadEvents(env) {
  const cached = await env.RISK_KV.get(EVENTS_CACHE_KEY, { type: "json" });
  if (cached) return cached;

  const obj = await env.RISK_R2.get("all_events.json");
  if (!obj) return null;

  const text = await obj.text();
  const data = JSON.parse(text);
  await env.RISK_KV.put(EVENTS_CACHE_KEY, text, { expirationTtl: EVENTS_CACHE_TTL });
  return data;
}

// ---------------------------------------------------------------------------
// Weather multiplier helpers
// ---------------------------------------------------------------------------

function weatherMultipliers(weatherType, precipProb) {
  // Heavy rain / storm increases incident risk, decreases escape ability
  let incident = 1.0;
  let escape = 1.0;

  if (weatherType === "storm" || weatherType === "typhoon") {
    incident = 1.5 + precipProb * 0.5;
    escape = 0.5 - precipProb * 0.2;
  } else if (weatherType === "rain" || weatherType === "heavy_rain") {
    incident = 1.2 + precipProb * 0.3;
    escape = 0.7 - precipProb * 0.1;
  } else if (weatherType === "snow") {
    incident = 1.3 + precipProb * 0.3;
    escape = 0.6 - precipProb * 0.15;
  } else if (weatherType === "cloudy") {
    incident = 1.05;
    escape = 0.95;
  }
  // clear / sunny: multipliers stay at 1.0

  return {
    incident_multiplier: Math.round(Math.max(0.5, incident) * 1000) / 1000,
    escape_multiplier: Math.round(Math.max(0.2, Math.min(1.0, escape)) * 1000) / 1000,
  };
}

// ---------------------------------------------------------------------------
// Temporal multiplier helpers
// ---------------------------------------------------------------------------

function temporalMultiplier(hour) {
  // Late night (22-04) highest risk, morning (6-9) moderate, daytime low, evening moderate-high
  if (hour >= 22 || hour < 4) return { incident: 1.4, escape: 0.7, label: "deep_night" };
  if (hour >= 4 && hour < 6) return { incident: 1.2, escape: 0.8, label: "early_morning" };
  if (hour >= 6 && hour < 9) return { incident: 1.0, escape: 0.95, label: "morning" };
  if (hour >= 9 && hour < 17) return { incident: 0.8, escape: 1.0, label: "daytime" };
  if (hour >= 17 && hour < 20) return { incident: 1.1, escape: 0.9, label: "evening" };
  return { incident: 1.25, escape: 0.8, label: "night" }; // 20-22
}

// ---------------------------------------------------------------------------
// GET /mcp/get_weather?pref=東京都&hour=22
// ---------------------------------------------------------------------------

async function handleGetWeather(url, env) {
  const { pref, hour } = params(url, { pref: "", hour: -1 });

  if (!pref) {
    return json({ error: "pref is required (e.g. pref=東京都)" }, 400);
  }

  // Check KV cache
  const cacheKey = `cache:weather:${pref}:${hour}`;
  const cached = await env.RISK_KV.get(cacheKey, { type: "json" });
  if (cached) return json({ ...cached, cached: true });

  const forecasts = await loadWeather(env);
  if (!forecasts) {
    return json({ error: "forecasts_all.json not found in R2" }, 404);
  }

  // forecasts can be an array or object with prefecture keys
  let prefForecasts = [];
  if (Array.isArray(forecasts)) {
    prefForecasts = forecasts.filter(
      (f) => f.pref === pref || f.prefecture === pref || (f.area && f.area.includes(pref))
    );
  } else if (forecasts[pref]) {
    prefForecasts = Array.isArray(forecasts[pref]) ? forecasts[pref] : [forecasts[pref]];
  }

  if (prefForecasts.length === 0) {
    return json({ pref, hour, error: "No forecast data found for this prefecture" }, 404);
  }

  // Find closest forecast to requested hour
  let best = prefForecasts[0];
  if (hour >= 0) {
    let bestDiff = Infinity;
    for (const f of prefForecasts) {
      const fHour = f.hour != null ? f.hour : (f.time ? parseInt(f.time.split(":")[0]) : 12);
      const diff = Math.abs(fHour - hour);
      const wrapDiff = Math.min(diff, 24 - diff);
      if (wrapDiff < bestDiff) {
        bestDiff = wrapDiff;
        best = f;
      }
    }
  }

  const weatherType = best.weather_type || best.weather || best.type || "unknown";
  const precipProb = best.precip_prob != null ? best.precip_prob : (best.precipitation_probability != null ? best.precipitation_probability / 100 : 0);
  const mults = weatherMultipliers(weatherType, precipProb);

  const result = {
    pref,
    hour: hour >= 0 ? hour : (best.hour || null),
    weather_type: weatherType,
    precip_prob: precipProb,
    incident_multiplier: mults.incident_multiplier,
    escape_multiplier: mults.escape_multiplier,
    cached: false,
  };

  // Cache for 1 hour
  await env.RISK_KV.put(cacheKey, JSON.stringify(result), { expirationTtl: 3600 });

  return json(result);
}

// ---------------------------------------------------------------------------
// GET /mcp/get_events?pref=東京都&date=2026-04-04
// ---------------------------------------------------------------------------

async function handleGetEvents(url, env) {
  const { pref, date } = params(url, { pref: "", date: "" });

  if (!pref) {
    return json({ error: "pref is required" }, 400);
  }
  if (!date) {
    return json({ error: "date is required (e.g. date=2026-04-04)" }, 400);
  }

  // Check KV cache
  const cacheKey = `cache:events:${pref}:${date}`;
  const cached = await env.RISK_KV.get(cacheKey, { type: "json" });
  if (cached) return json({ ...cached, cached: true });

  const allEvents = await loadEvents(env);
  if (!allEvents) {
    return json({ error: "all_events.json not found in R2" }, 404);
  }

  const activeEvents = [];
  let incidentMult = 1.0;
  let escapeMult = 1.0;
  let crowdMult = 1.0;

  // Check holidays
  const holidays = allEvents.holidays || [];
  for (const h of holidays) {
    const hDate = h.date || h.start_date;
    if (hDate === date) {
      activeEvents.push({ type: "holiday", name: h.name || h.title, source: "holidays" });
      incidentMult *= 1.15; // holidays: slightly higher incident risk
      crowdMult *= 1.4; // more people out
      escapeMult *= 0.9; // crowded escape routes
    }
  }

  // Check calendar events
  const calendar = allEvents.calendar_events || allEvents.calendar || [];
  for (const ev of calendar) {
    const evDate = ev.date || ev.start_date;
    const evEnd = ev.end_date || evDate;
    if (evDate <= date && date <= evEnd) {
      const prefMatch = !ev.pref || ev.pref === pref || ev.prefecture === pref || ev.area === "全国";
      if (prefMatch) {
        activeEvents.push({ type: "calendar", name: ev.name || ev.title, source: "calendar" });
        incidentMult *= (ev.incident_multiplier || 1.1);
        crowdMult *= (ev.crowd_multiplier || 1.2);
        escapeMult *= (ev.escape_multiplier || 0.95);
      }
    }
  }

  // Check scraped events
  const scraped = allEvents.scraped_events || allEvents.events || [];
  for (const ev of scraped) {
    const evDate = ev.date || ev.start_date;
    const evEnd = ev.end_date || evDate;
    if (evDate && evDate <= date && date <= (evEnd || evDate)) {
      const prefMatch = !ev.pref || ev.pref === pref || ev.prefecture === pref;
      if (prefMatch) {
        activeEvents.push({
          type: "event",
          name: ev.name || ev.title,
          venue: ev.venue || null,
          expected_attendance: ev.attendance || ev.expected_attendance || null,
          source: "scraped",
        });
        const scale = ev.attendance > 50000 ? 1.3 : ev.attendance > 10000 ? 1.15 : 1.05;
        incidentMult *= (ev.incident_multiplier || scale);
        crowdMult *= (ev.crowd_multiplier || scale);
        escapeMult *= (ev.escape_multiplier || (1 / scale));
      }
    }
  }

  const result = {
    pref,
    date,
    active_events: activeEvents,
    incident_multiplier: Math.round(incidentMult * 1000) / 1000,
    escape_multiplier: Math.round(Math.max(0.2, escapeMult) * 1000) / 1000,
    crowd_multiplier: Math.round(crowdMult * 1000) / 1000,
    cached: false,
  };

  // Cache for 1 hour
  await env.RISK_KV.put(cacheKey, JSON.stringify(result), { expirationTtl: 3600 });

  return json(result);
}

// ---------------------------------------------------------------------------
// GET /mcp/get_dynamic_risk?lat=X&lon=X&radius_km=X&pref=東京都&hour=22&date=2026-04-04
// Combines get_risk_field + get_weather + get_events + temporal multipliers
// ---------------------------------------------------------------------------

async function handleGetDynamicRisk(url, env) {
  const { lat, lon, radius_km, pref, hour, date, layers } = params(url, {
    lat: 0,
    lon: 0,
    radius_km: 1,
    pref: "",
    hour: -1,
    date: "",
    layers: "crime,traffic,disaster,weather",
  });

  if (lat === 0 && lon === 0) {
    return json({ error: "lat and lon are required" }, 400);
  }

  // 1. Get base risk field
  const riskUrl = new URL(url.toString());
  const riskResponse = await handleGetRiskField(riskUrl, env);
  const riskData = await riskResponse.json();

  // 2. Get weather multipliers (if pref provided)
  let weatherData = null;
  if (pref) {
    try {
      const weatherUrl = new URL(url.origin + "/mcp/get_weather?pref=" + encodeURIComponent(pref) + "&hour=" + hour);
      const weatherResp = await handleGetWeather(weatherUrl, env);
      weatherData = await weatherResp.json();
    } catch (e) {
      weatherData = { incident_multiplier: 1, escape_multiplier: 1, error: e.message };
    }
  }

  // 3. Get events multipliers (if pref and date provided)
  let eventsData = null;
  if (pref && date) {
    try {
      const eventsUrl = new URL(url.origin + "/mcp/get_events?pref=" + encodeURIComponent(pref) + "&date=" + date);
      const eventsResp = await handleGetEvents(eventsUrl, env);
      eventsData = await eventsResp.json();
    } catch (e) {
      eventsData = { incident_multiplier: 1, escape_multiplier: 1, crowd_multiplier: 1, error: e.message };
    }
  }

  // 4. Temporal multiplier
  const effectiveHour = hour >= 0 ? hour : new Date().getUTCHours() + 9; // JST
  const temporal = temporalMultiplier(effectiveHour % 24);

  // 5. Combine all multipliers
  const baseScore = riskData.risk_score || 0;
  const weatherInc = weatherData ? weatherData.incident_multiplier : 1;
  const weatherEsc = weatherData ? weatherData.escape_multiplier : 1;
  const eventsInc = eventsData ? eventsData.incident_multiplier : 1;
  const eventsEsc = eventsData ? eventsData.escape_multiplier : 1;
  const crowdMult = eventsData ? eventsData.crowd_multiplier : 1;

  const combinedIncident = baseScore * weatherInc * eventsInc * temporal.incident;
  const combinedEscape = weatherEsc * eventsEsc * temporal.escape;
  const dynamicRisk = Math.min(1.0, combinedIncident * (1 + (1 - combinedEscape) * 0.5) * crowdMult);

  return json({
    lat,
    lon,
    radius_km,
    pref: pref || null,
    date: date || null,
    hour: effectiveHour % 24,

    // Base risk
    base_risk_score: baseScore,
    base_risk_level: riskData.risk_level || "low",
    cells_found: riskData.cells_found || 0,
    breakdown: riskData.breakdown || {},

    // Multipliers
    multipliers: {
      weather: weatherData ? {
        incident: weatherInc,
        escape: weatherEsc,
        weather_type: weatherData.weather_type,
        precip_prob: weatherData.precip_prob,
      } : null,
      events: eventsData ? {
        incident: eventsInc,
        escape: eventsEsc,
        crowd: crowdMult,
        active_events: eventsData.active_events || [],
      } : null,
      temporal: {
        incident: temporal.incident,
        escape: temporal.escape,
        period: temporal.label,
      },
    },

    // Combined dynamic risk
    dynamic_risk_score: Math.round(dynamicRisk * 10000) / 10000,
    dynamic_risk_level: dynamicRisk >= 0.8 ? "critical" : dynamicRisk >= 0.6 ? "high" : dynamicRisk >= 0.3 ? "medium" : "low",
    combined_escape_probability: Math.round(combinedEscape * 10000) / 10000,

    // Expected harm (dynamic)
    dynamic_expected_harm: Math.round(dynamicRisk * (1 - combinedEscape) * 10000) / 10000,

    timestamp: new Date().toISOString(),
  });
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
      if (method === "GET" && pathname === "/mcp/get_weather") {
        return await handleGetWeather(url, env);
      }
      if (method === "GET" && pathname === "/mcp/get_events") {
        return await handleGetEvents(url, env);
      }
      if (method === "GET" && pathname === "/mcp/get_dynamic_risk") {
        return await handleGetDynamicRisk(url, env);
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
            "GET  /mcp/get_weather?pref=東京都&hour=22",
            "GET  /mcp/get_events?pref=東京都&date=2026-04-04",
            "GET  /mcp/get_dynamic_risk?lat=X&lon=X&radius_km=X&pref=東京都&hour=22&date=2026-04-04",
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
