# Risk Space MCP — ツール設計書 v1.0

## ツール一覧（優先順位順）

### 1. get_signals
引数: lat, lon, radius_km, time_window_hours, layers[]
返却: [{layer, subtype, occurred_at, severity, source, geometry, distance_km}]

### 2. get_hotspots
引数: prefecture, layer, date_from, date_to, limit
返却: [{lat, lon, risk_score, event_count, dominant_subtype}]

### 3. get_risk_field
引数: lat, lon, radius_km, time, layers[]
返却: {risk_score, breakdown_by_layer, events_count, data_freshness}

### 4. get_risk_timeline
引数: lat, lon, radius_km, period_days
返却: [{date, risk_score, dominant_layer, event_count}]

### 5. update_field（ユーザー通報）
引数: event_type, lat, lon, timestamp, severity, description
返却: {id, risk_score_before, risk_score_after}

## Cloudflare Workers + R2 + KV 構成
- Workers: MCPエンドポイント・リスク計算
- R2: 正規化JSON（normalized/）の格納
- KV: リアルタイムキャッシュ（気象・地震・不審者情報）TTL=300秒
- D1: 空間Geohash・時間パーティションインデックス

## 更新頻度戦略
| レイヤー | ソース | 更新頻度 | キャッシュTTL |
|---|---|---|---|
| weather（地震・警報）| 気象庁 | リアルタイム | 60秒 |
| weather（アメダス）| 気象庁 | 10分 | 600秒 |
| crime（不審者情報）| メールけいしちょう | 随時 | 3600秒 |
| crime（犯罪発生）| 都道府県警CSV | 月次 | 1日 |
| traffic（交通事故）| 警察庁 | 年次 | 1週間 |
| evacuation（避難場所）| 国土地理院 | 静的 | 1ヶ月 |
