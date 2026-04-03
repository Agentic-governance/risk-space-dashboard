/**
 * Risk Space LINE Bot — Cloudflare Workers
 *
 * Receives LINE webhook events and responds with risk information
 * from the Risk Space MCP endpoint.
 *
 * Message handlers:
 *   Location message → get_risk_field → risk analysis
 *   "今から帰る"     → record departure, show current risk
 *   "ついた"         → confirm safe arrival
 *   "不審者"/"危ない" → report to MCP update_field
 *   "ホットスポット"  → get_hotspots top 3
 *   "パトロール"     → recommended patrol areas
 *   Default          → show help menu
 */

// ---------------------------------------------------------------------------
// LINE signature verification (HMAC-SHA256)
// ---------------------------------------------------------------------------

async function verifySignature(body, signature, channelSecret) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(channelSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const expected = btoa(String.fromCharCode(...new Uint8Array(sig)));
  return expected === signature;
}

// ---------------------------------------------------------------------------
// LINE Messaging API helpers
// ---------------------------------------------------------------------------

const LINE_API = "https://api.line.me/v2/bot/message";

async function replyMessage(replyToken, messages, channelAccessToken) {
  if (!Array.isArray(messages)) messages = [messages];

  // Ensure all messages are objects
  const formatted = messages.map((m) =>
    typeof m === "string" ? { type: "text", text: m } : m
  );

  const res = await fetch(`${LINE_API}/reply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${channelAccessToken}`,
    },
    body: JSON.stringify({ replyToken, messages: formatted.slice(0, 5) }),
  });

  if (!res.ok) {
    const err = await res.text();
    console.error("LINE reply failed:", res.status, err);
  }
  return res;
}

function textMsg(text) {
  return { type: "text", text };
}

// ---------------------------------------------------------------------------
// MCP API client
// ---------------------------------------------------------------------------

async function mcpFetch(env, path) {
  const base = env.MCP_BASE_URL || "https://risk-space-mcp.YOUR_SUBDOMAIN.workers.dev";
  const res = await fetch(`${base}${path}`);
  if (!res.ok) throw new Error(`MCP ${path} returned ${res.status}`);
  return res.json();
}

async function mcpPost(env, path, body) {
  const base = env.MCP_BASE_URL || "https://risk-space-mcp.YOUR_SUBDOMAIN.workers.dev";
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`MCP POST ${path} returned ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Risk level emoji & formatting
// ---------------------------------------------------------------------------

function riskEmoji(level) {
  if (level === "high") return "\u{1F534}"; // red circle
  if (level === "medium") return "\u{1F7E1}"; // yellow circle
  return "\u{1F7E2}"; // green circle
}

function riskBar(score) {
  const filled = Math.round(score * 10);
  return "\u2588".repeat(filled) + "\u2591".repeat(10 - filled);
}

function layerLabel(layer) {
  const map = {
    crime: "\u{1F6A8} 犯罪",
    traffic: "\u{1F697} 交通事故",
    disaster: "\u{1F30A} 災害",
    weather: "\u{26C8}\uFE0F 気象",
  };
  return map[layer] || layer;
}

function subtypeLabel(subtype) {
  const map = {
    theft_bicycle: "自転車盗",
    theft_motorcycle: "オートバイ盗",
    theft_vehicle: "自動車盗",
    theft_car_breakin: "車上ねらい",
    theft_purse_snatching: "ひったくり",
    collision_injury: "負傷事故",
    collision_fatal: "死亡事故",
    quake: "地震",
    user_report: "住民通報",
  };
  return map[subtype] || subtype;
}

// ---------------------------------------------------------------------------
// Message handlers
// ---------------------------------------------------------------------------

/**
 * Location message → call get_risk_field, return risk analysis
 */
async function handleLocation(event, env) {
  const { latitude, longitude } = event.message;
  const radiusKm = 1;

  try {
    const data = await mcpFetch(
      env,
      `/mcp/get_risk_field?lat=${latitude}&lon=${longitude}&radius_km=${radiusKm}&layers=crime,traffic,disaster,weather`
    );

    if (data.cells_found === 0) {
      return textMsg(
        `\u{1F4CD} この地点（${latitude.toFixed(4)}, ${longitude.toFixed(4)}）周辺${radiusKm}km以内にリスクデータがありません。\n\n郊外や海域の場合はデータ範囲外の可能性があります。`
      );
    }

    let text = `\u{1F4CD} リスク分析結果\n`;
    text += `━━━━━━━━━━━━━━━\n`;
    text += `${riskEmoji(data.risk_level)} 総合リスク: ${(data.risk_score * 100).toFixed(1)}%\n`;
    text += `${riskBar(data.risk_score)}\n`;
    text += `レベル: ${data.risk_level === "high" ? "高" : data.risk_level === "medium" ? "中" : "低"}\n`;
    text += `分析セル数: ${data.cells_found}\n\n`;

    // Layer breakdown
    if (data.breakdown && Object.keys(data.breakdown).length > 0) {
      text += `\u{1F4CA} レイヤー別:\n`;
      for (const [layer, info] of Object.entries(data.breakdown)) {
        text += `  ${layerLabel(layer)}: ${info.event_count}件 (${(info.weighted_score * 100).toFixed(1)}%)\n`;
      }
      text += `\n`;
    }

    // Top subtypes
    if (data.top_subtypes && data.top_subtypes.length > 0) {
      text += `\u{1F50D} 主な事象:\n`;
      for (const st of data.top_subtypes.slice(0, 3)) {
        text += `  - ${subtypeLabel(st.subtype)}: ${st.count}件\n`;
      }
    }

    return textMsg(text.trim());
  } catch (err) {
    console.error("get_risk_field error:", err);
    return textMsg(`\u26A0\uFE0F リスクデータの取得に失敗しました。しばらくしてからお試しください。`);
  }
}

/**
 * "今から帰る" → record departure time in KV, show current risk
 */
async function handleDeparture(event, env) {
  const userId = event.source.userId;
  const now = new Date().toISOString();

  // Store departure info
  await env.LINE_KV.put(
    `trip:${userId}`,
    JSON.stringify({ status: "departed", departed_at: now }),
    { expirationTtl: 7200 } // 2 hours
  );

  // Try to get user's last known location for risk info
  const lastLoc = await env.LINE_KV.get(`location:${userId}`, { type: "json" });

  let text = `\u{1F3E0} 帰宅モード開始\n`;
  text += `出発時刻: ${new Date(now).toLocaleTimeString("ja-JP", { timeZone: "Asia/Tokyo" })}\n\n`;

  if (lastLoc) {
    try {
      const data = await mcpFetch(
        env,
        `/mcp/get_risk_field?lat=${lastLoc.lat}&lon=${lastLoc.lon}&radius_km=1&layers=crime`
      );
      text += `${riskEmoji(data.risk_level)} 周辺の犯罪リスク: ${(data.risk_score * 100).toFixed(1)}%\n\n`;
    } catch {
      // ignore — just skip risk info
    }
  }

  text += `\u{2705} 到着したら「ついた」と送ってください。\n`;
  text += `\u{26A0}\uFE0F 2時間以内に到着連絡がない場合、記録が自動削除されます。`;

  return textMsg(text);
}

/**
 * "ついた" → confirm safe arrival
 */
async function handleArrival(event, env) {
  const userId = event.source.userId;
  const trip = await env.LINE_KV.get(`trip:${userId}`, { type: "json" });

  if (!trip || trip.status !== "departed") {
    return textMsg(`\u{2139}\uFE0F 現在、帰宅モードは有効ではありません。\n「今から帰る」で開始できます。`);
  }

  const departedAt = new Date(trip.departed_at);
  const arrivedAt = new Date();
  const durationMin = Math.round((arrivedAt - departedAt) / 60000);

  // Update trip record
  await env.LINE_KV.put(
    `trip:${userId}`,
    JSON.stringify({
      status: "arrived",
      departed_at: trip.departed_at,
      arrived_at: arrivedAt.toISOString(),
      duration_min: durationMin,
    }),
    { expirationTtl: 86400 }
  );

  return textMsg(
    `\u{2705} 無事到着を確認しました！\n\n` +
    `出発: ${departedAt.toLocaleTimeString("ja-JP", { timeZone: "Asia/Tokyo" })}\n` +
    `到着: ${arrivedAt.toLocaleTimeString("ja-JP", { timeZone: "Asia/Tokyo" })}\n` +
    `所要時間: ${durationMin}分\n\n` +
    `お疲れさまでした \u{1F44D}`
  );
}

/**
 * "不審者"/"危ない" → report to MCP update_field
 */
async function handleDangerReport(event, env) {
  const userId = event.source.userId;
  const messageText = event.message.text;

  // Determine subtype from message
  let subtype = "user_report";
  let layer = "crime";
  if (messageText.includes("不審者")) subtype = "suspicious_person";
  if (messageText.includes("事故")) {
    subtype = "collision";
    layer = "traffic";
  }

  // Check for last known location
  const lastLoc = await env.LINE_KV.get(`location:${userId}`, { type: "json" });

  if (!lastLoc) {
    return textMsg(
      `\u{26A0}\uFE0F 通報を受け付けるには位置情報が必要です。\n\n` +
      `LINE画面下部の「+」ボタン → 「位置情報」から現在地を送信した後、もう一度通報してください。`
    );
  }

  try {
    const result = await mcpPost(env, "/mcp/update_field", {
      lat: lastLoc.lat,
      lon: lastLoc.lon,
      layer,
      subtype,
      severity: 3,
      description: messageText,
      reporter_id: `line:${userId.substring(0, 8)}`,
    });

    return textMsg(
      `\u{1F6A8} 通報を受け付けました\n\n` +
      `種別: ${subtypeLabel(subtype)}\n` +
      `位置: ${lastLoc.lat.toFixed(4)}, ${lastLoc.lon.toFixed(4)}\n` +
      `ID: ${result.id?.substring(0, 8) || "---"}\n\n` +
      `周辺住民への情報共有に活用されます。ありがとうございます。`
    );
  } catch (err) {
    console.error("update_field error:", err);
    return textMsg(`\u{26A0}\uFE0F 通報の送信に失敗しました。しばらくしてからお試しください。`);
  }
}

/**
 * "ホットスポット" → call get_hotspots, show top 3
 */
async function handleHotspots(event, env) {
  try {
    const data = await mcpFetch(env, `/mcp/get_hotspots?layer=all&limit=3`);

    let text = `\u{1F525} リスクホットスポット TOP3\n`;
    text += `━━━━━━━━━━━━━━━\n\n`;

    if (!data.hotspots || data.hotspots.length === 0) {
      text += `データがありません。`;
      return textMsg(text);
    }

    data.hotspots.forEach((h, i) => {
      const rank = ["1\uFE0F\u20E3", "2\uFE0F\u20E3", "3\uFE0F\u20E3"][i];
      text += `${rank} リスク ${(h.risk_score * 100).toFixed(0)}%\n`;
      text += `   \u{1F4CD} ${h.lat.toFixed(2)}, ${h.lon.toFixed(2)}\n`;
      text += `   事象数: ${h.event_count}件\n`;
      if (h.dominant_subtype) {
        text += `   主要: ${subtypeLabel(h.dominant_subtype)}\n`;
      }
      // Layer breakdown
      if (h.layers) {
        const parts = Object.entries(h.layers)
          .filter(([, v]) => v > 0)
          .map(([k, v]) => `${layerLabel(k)}${v}件`);
        text += `   ${parts.join(" / ")}\n`;
      }
      text += `\n`;
    });

    return textMsg(text.trim());
  } catch (err) {
    console.error("get_hotspots error:", err);
    return textMsg(`\u{26A0}\uFE0F ホットスポットデータの取得に失敗しました。`);
  }
}

/**
 * "パトロール" → show recommended patrol areas
 */
async function handlePatrol(event, env) {
  try {
    // Get high-crime hotspots
    const data = await mcpFetch(env, `/mcp/get_hotspots?layer=crime&limit=5`);

    let text = `\u{1F6B6} パトロール推奨エリア\n`;
    text += `━━━━━━━━━━━━━━━\n\n`;

    if (!data.hotspots || data.hotspots.length === 0) {
      text += `現在、特に注意が必要なエリアはありません。`;
      return textMsg(text);
    }

    data.hotspots.forEach((h, i) => {
      text += `${i + 1}. \u{1F4CD} ${h.lat.toFixed(3)}, ${h.lon.toFixed(3)}\n`;
      text += `   犯罪リスク: ${(h.risk_score * 100).toFixed(0)}% / ${h.event_count}件\n`;
      if (h.dominant_subtype) {
        text += `   注意: ${subtypeLabel(h.dominant_subtype)}\n`;
      }
      text += `\n`;
    });

    text += `\u{1F4A1} 上記エリアの重点巡回をお勧めします。\n`;
    text += `位置情報を送ると、そのエリアの詳細リスクを確認できます。`;

    return textMsg(text.trim());
  } catch (err) {
    console.error("patrol error:", err);
    return textMsg(`\u{26A0}\uFE0F パトロール情報の取得に失敗しました。`);
  }
}

/**
 * Default → show help menu
 */
function handleHelp() {
  const text =
    `\u{1F6E1}\uFE0F Risk Space Bot ヘルプ\n` +
    `━━━━━━━━━━━━━━━\n\n` +
    `\u{1F4CD} 位置情報を送信\n` +
    `  → その地点のリスク分析\n\n` +
    `\u{1F3E0} 「今から帰る」\n` +
    `  → 帰宅モード開始\n\n` +
    `\u{2705} 「ついた」\n` +
    `  → 到着確認\n\n` +
    `\u{1F6A8} 「不審者」「危ない」\n` +
    `  → 危険通報（要・位置情報送信済み）\n\n` +
    `\u{1F525} 「ホットスポット」\n` +
    `  → リスク上位3地点を表示\n\n` +
    `\u{1F6B6} 「パトロール」\n` +
    `  → 巡回推奨エリアを表示\n\n` +
    `\u{2139}\uFE0F まずは位置情報を送ってみてください！`;

  return textMsg(text);
}

// ---------------------------------------------------------------------------
// Webhook event router
// ---------------------------------------------------------------------------

async function handleEvent(event, env) {
  // Only handle message events
  if (event.type !== "message") return null;

  const { message } = event;

  // Location message
  if (message.type === "location") {
    // Store last known location
    const userId = event.source.userId;
    if (userId) {
      await env.LINE_KV.put(
        `location:${userId}`,
        JSON.stringify({ lat: message.latitude, lon: message.longitude, at: new Date().toISOString() }),
        { expirationTtl: 86400 }
      );
    }
    return handleLocation(event, env);
  }

  // Text message
  if (message.type === "text") {
    const text = message.text.trim();

    if (text.includes("今から帰る") || text.includes("帰る") || text === "帰宅") {
      return handleDeparture(event, env);
    }
    if (text === "ついた" || text === "到着" || text.includes("着いた")) {
      return handleArrival(event, env);
    }
    if (text.includes("不審者") || text.includes("危ない") || text.includes("危険") || text.includes("通報")) {
      return handleDangerReport(event, env);
    }
    if (text.includes("ホットスポット") || text === "hotspot") {
      return handleHotspots(event, env);
    }
    if (text.includes("パトロール") || text === "patrol") {
      return handlePatrol(event, env);
    }

    // Default: help
    return handleHelp();
  }

  // Other message types (sticker, image, etc.) → help
  return handleHelp();
}

// ---------------------------------------------------------------------------
// Main fetch handler
// ---------------------------------------------------------------------------

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const { pathname } = url;

    // Health check
    if (request.method === "GET" && pathname === "/health") {
      return new Response(
        JSON.stringify({ status: "ok", timestamp: new Date().toISOString() }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    // LINE webhook endpoint
    if (request.method === "POST" && pathname === "/webhook") {
      const signature = request.headers.get("x-line-signature");
      if (!signature) {
        return new Response("Missing signature", { status: 400 });
      }

      const body = await request.text();

      // Verify HMAC-SHA256 signature
      const valid = await verifySignature(body, signature, env.LINE_CHANNEL_SECRET);
      if (!valid) {
        console.error("Invalid LINE signature");
        return new Response("Invalid signature", { status: 403 });
      }

      let payload;
      try {
        payload = JSON.parse(body);
      } catch {
        return new Response("Invalid JSON", { status: 400 });
      }

      const events = payload.events || [];

      // Process all events (use waitUntil so we can return 200 quickly)
      const promises = events.map(async (event) => {
        try {
          const reply = await handleEvent(event, env);
          if (reply && event.replyToken) {
            await replyMessage(event.replyToken, reply, env.LINE_CHANNEL_ACCESS_TOKEN);
          }
        } catch (err) {
          console.error("Event handling error:", err, JSON.stringify(event));
        }
      });

      ctx.waitUntil(Promise.all(promises));

      // LINE expects 200 OK quickly
      return new Response("OK", { status: 200 });
    }

    // Default
    return new Response("Risk Space LINE Bot", { status: 200 });
  },
};
