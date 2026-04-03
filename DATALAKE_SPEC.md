# Risk Space MCP — データレイク & 処理パイプライン仕様書

**最終更新**: 2026-04-04
**総イベント**: 2,270,784件
**Safe Haven**: 174,911施設
**適応メッシュ**: 334,447セル (ダッシュボードは上位10,000セルを配信)

---

## 1. データレイク構成

```
data/
├── crime/                          # 犯罪データ
│   ├── prefectures/                # 22都道府県警CSV (492ファイル)
│   │   ├── 東京都/                 # 29,043件 (2024)
│   │   ├── 大阪府/                 # ~234,000件 (2018-2024)
│   │   ├── 神奈川県/               # ~101,000件 (2018-2024)
│   │   ├── 愛知県/                 # ~70,000件 (2019-2024)
│   │   ├── 兵庫県/                 # ~76,000件 (2018-2024)
│   │   ├── ...                     # 他17県 (各県1-7年分)
│   │   ├── download_results.json   # Phase1 結果
│   │   ├── phase2_results.json     # Phase2 結果
│   │   └── historical_download_results.json
│   ├── national/                   # 全国統計
│   │   ├── estat_crime_full.json   # e-Stat全犯罪種別×47都道府県 (3,980レコード)
│   │   ├── synthetic_events.json   # 25県合成イベント (189,821件, 50MB)
│   │   ├── pref_centroids.json     # 47都道府県重心座標
│   │   └── city_centroids.json     # 893市区町村重心座標
│   └── estat_*.json                # e-Stat生データ (9ファイル)
│
├── traffic/                        # 交通事故データ
│   ├── honhyo_2019.csv             # 381,237件
│   ├── honhyo_2020.csv             # 309,178件
│   ├── honhyo_2022.csv             # 300,839件
│   ├── honhyo_2023.csv             # 307,930件
│   └── honhyo_2024_full.csv        # 290,895件 (59MB)
│
├── normalized/                     # 正規化済みデータ
│   ├── crime_all.json              # 東京都 29,043件 (28,936件ジオコーディング済)
│   ├── crime_national.json         # 22県正規化 151,059件 (133MB)
│   ├── traffic_collision.json      # 旧50,000サンプル
│   ├── traffic_collision_full.json # 全件 1,590,079件 (1.4GB)
│   ├── disaster_quake.json         # 地震 244件 (216件座標あり)
│   ├── all_events_scored_v2.json   # リスクスコア付き
│   ├── hotspots_v2.json            # ホットスポット上位20
│   └── adaptive_mesh.json          # 適応メッシュ 334,447セル
│
├── geocoded/                       # ジオコーディング結果
│   ├── all_crime_geocoded_full.json  # 東京都全件 28,936/29,043成功
│   └── geocoding_progress.json       # 進捗状態
│
├── safe_haven/                     # Safe Haven施設データ
│   ├── ALL_HAVENS.json             # 統合 174,911施設 (24MB)
│   ├── police/
│   │   ├── police_ksj.json         # 国土数値情報P18: 37,422件
│   │   ├── police_osm.json         # OpenStreetMap: 17,608件
│   │   └── raw/                    # P18 Shapefile原本
│   ├── fire/
│   │   ├── fire_ksj.json           # 国土数値情報P17: 42,394件
│   │   └── raw/                    # P17 Shapefile原本
│   ├── hospital/
│   │   ├── hospitals_all.json      # 厚労省+OSM: 18,432件
│   │   ├── arrival_times.json      # 都道府県別救急到着時間 (48エントリ)
│   │   └── kyukyu_genkyo.pdf       # 消防庁PDF原本
│   ├── aed/
│   │   ├── aed_osm.json            # OSM+BODIK: 13,545件
│   │   └── bodik_*.csv             # BODIK AED生データ
│   ├── convenience/
│   │   └── havens_osm.json         # コンビニ・駅等: 45,510件
│   └── evacuation/                 # G空間避難場所 (20ファイル, 14県)
│
├── realtime/                       # リアルタイムデータ
│   ├── fushinsha_live/             # 不審者クローラー出力
│   │   ├── events_*.json           # 30分間隔クロール結果
│   │   └── seen_hashes.json        # 重複排除ハッシュ
│   ├── news/
│   │   ├── nhk_events.json         # NHK RSS: 7件
│   │   └── crime_news.json         # 新聞社クロール: 27件
│   ├── sns/
│   │   └── yahoo_realtime.json     # Yahoo!リアルタイム: 60件
│   ├── fushinsha/
│   │   └── all_fushinsha.json      # ガッコム等: 68件
│   ├── jaspic_analysis/
│   │   ├── schema_samples.json     # JASPIC記事解析 (31件)
│   │   └── kind_taxonomy.json      # 37種別分類
│   ├── source_map.json             # 47都道府県URLマスター
│   └── comparison_report.json      # JASPIC比較
│
├── competitive_analysis.json       # 競合5社分析
│
└── proxy/                          # 代理指標（未実装）
    ├── land_price/                 # 地価公示 (APIキー必要)
    └── population/                 # 人口密度
```

---

## 2. データソース一覧

### 2-1. イベントデータ (2,270,784件)

| # | ソース | レイヤー | 件数 | 期間 | 更新頻度 | 座標精度 | ライセンス |
|---|---|---|---|---|---|---|---|
| 1 | 警視庁 犯罪CSV | crime | 29,043 | 2024 | 月次 | 町丁目(API) | 政府標準 |
| 2 | 21都道府県警 犯罪CSV | crime | 432,824 | 2018-2024 | 月次-年次 | 市区町村重心 | 政府標準 |
| 3 | e-Stat合成 (25県) | crime | 189,821 | 2023 | 年次 | 市区町村按分 | 政府標準 |
| 4 | 警察庁 交通事故CSV | traffic | 1,590,079 | 2019-2024 | 年次 | 地点(DMS) | 政府標準 |
| 5 | 気象庁 地震情報 | disaster | 216 | 2024 | リアルタイム | 震源(ISO6709) | 政府標準 |
| 6 | JASPIC不審者 | crime | 31 | 2026 | リアルタイム | 市区町村 | 報道利用 |
| 7 | NHK RSS | crime/disaster | 7 | 2026 | リアルタイム | 住所抽出 | 報道利用 |
| 8 | Yahoo!リアルタイム | crime | 60 | 2026 | リアルタイム | 住所抽出 | スクレイピング |
| 9 | ガッコム安全ナビ | crime | 68 | 2026 | リアルタイム | 住所 | スクレイピング |
| 10 | 新聞社クロール | crime | 27 | 2026 | リアルタイム | 住所抽出 | 報道利用 |

### 2-2. Safe Haven施設データ (174,911件)

| # | ソース | 施設種別 | 件数 | 座標精度 | ライセンス |
|---|---|---|---|---|---|
| 1 | 国土数値情報 P18 | 交番・警察署 | 37,422 | 建物位置 | 政府標準 |
| 2 | OpenStreetMap | 交番・警察 | 17,608 | ポイント | ODbL |
| 3 | 国土数値情報 P17 | 消防署 | 42,394 | 建物位置 | 政府標準 |
| 4 | 厚労省 | 救命救急センター | 625 | 住所(要GC) | 政府標準 |
| 5 | OpenStreetMap | 病院 | 17,807 | ポイント | ODbL |
| 6 | BODIK CKAN | AED | 9,922 | ポイント | CC BY等 |
| 7 | OpenStreetMap | AED | 3,623 | ポイント | ODbL |
| 8 | OpenStreetMap | コンビニ | 34,761 | ポイント | ODbL |
| 9 | OpenStreetMap | 駅 | 9,307 | ポイント | ODbL |
| 10 | OpenStreetMap | その他24H | 1,442 | ポイント | ODbL |

### 2-3. 統計・補助データ

| ソース | 内容 | 件数 | 用途 |
|---|---|---|---|
| 消防庁PDF | 都道府県別救急到着時間 | 48 | P(escape)のarrival_score |
| e-Stat犯罪統計 | 全犯罪種別×47都道府県 | 3,980 | 合成イベント生成 |
| 気象庁アメダス | 1,286観測局 | 1,286 | 気象レイヤー(未統合) |
| 気象庁警報 | 警報・注意報 | 58 | 気象レイヤー(未統合) |
| G空間避難場所 | 避難施設 | 20ファイル | 避難レイヤー(未統合) |

---

## 3. 処理パイプライン

```
[生データ取得]
    │
    ▼
[正規化] ─── scripts/normalize_crime.py (犯罪CSV → 統一スキーマ)
    │         scripts/normalize_traffic_full.py (交通事故 → 統一スキーマ)
    │         scripts/collect_new_sources.py (NHK/Yahoo/河川)
    │
    ▼
[ジオコーディング]
    │  東京都: 国土地理院 msearch API (全件, 99.6%)
    │  22県: 市区町村重心座標マッピング (893市区町村, 99.3%)
    │  交通: DMS×1000 → WGS84 (全件, 100%)
    │  地震: ISO6709 cod解析 (88.5%)
    │
    ▼
[統合] ─── scripts/integrate_full.py
    │  全ソースをストリーム処理（ijson for 1.4GB traffic）
    │  ヒートマップ点群・グリッド・等高線マトリクスを同時生成
    │
    ▼
[適応メッシュ] ─── scripts/build_adaptive_mesh.py
    │  Quadtree分割: 250m(ultra) / 500m(high) / 1km(mid) / 5km(low)
    │  334,447セル生成
    │
    ▼
[Safe Haven統合] ─── scripts/task7_8_escape_harm.py
    │  174,911施設 → 0.1°空間インデックス
    │  各セルのP(escape)計算
    │
    ▼
[Expected Harm計算]
    │  Expected_Harm = P(incident) × (severity/5) × (1 - P(escape))
    │  50,000セルにp_escape + expected_harm付与
    │
    ▼
[ダッシュボード出力] ─── dashboard/data/
    │  events_compact.json (11MB, 227k件サンプル)
    │  grid_risk.json (2.8MB, 上位10kセル)
    │  heat_*.json (crime:15MB, traffic:36MB, disaster:8KB)
    │  contour_matrix.json (376KB, 221×321)
    │  hotspots_expected_harm.json / escape_deficit.json
    │
    ▼
[リアルタイム] ─── scripts/fushinsha_crawler.py --loop
       30分間隔: JASPIC nordot + 47都道府県URLマスター
```

---

## 4. スキーマ仕様

### 4-1. イベントスキーマ (共通)

```json
{
  "id": "uuid",
  "source_id": "string|null",
  "layer": "crime|traffic|disaster|weather",
  "subtype": "theft_bicycle|collision_injury|quake|...",
  "geometry": {
    "type": "Point",
    "coordinates": [lon, lat]
  },
  "admin": {
    "prefecture": "東京都",
    "prefecture_code": "13",
    "city": "新宿区",
    "city_code": "131041",
    "town": "歌舞伎町1丁目"
  },
  "spatial_resolution": "chome|city|prefecture",
  "occurred_at": "2024-01-15T22:30:00+09:00",
  "published_at": "ISO8601|null",
  "time_resolution": "minute|hour|day|month|year",
  "realtime": false,
  "severity": 3,
  "risk_score": 0.7234,
  "source": {
    "org": "警視庁",
    "url": "https://...",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "monthly",
    "missing_rate": 0.0,
    "geocoded": true
  },
  "raw": {}
}
```

### 4-2. Safe Havenスキーマ

```json
{
  "lat": 35.6895,
  "lon": 139.6917,
  "name": "新宿駅前交番",
  "type": "koban|fire_station|hospital|convenience_store|station|aed",
  "is_24h": true,
  "safety_score": 1.0,
  "source": "国土数値情報P18|OpenStreetMap|BODIK"
}
```

### 4-3. 適応メッシュセルスキーマ

```json
{
  "lat": 35.6895,
  "lon": 139.6917,
  "count": 156,
  "risk_score": 0.8234,
  "expected_harm": 0.5123,
  "p_escape": 0.582,
  "avg_severity": 2.8,
  "max_severity": 5,
  "resolution": "ultra|high|mid|low",
  "layers": {"crime": 80, "traffic": 76},
  "subtypes": {"theft_bicycle": 45, "collision_injury": 30},
  "haven_count_500m": 23,
  "nearest_haven_type": "convenience_store",
  "events": [...]
}
```

### 4-4. ダッシュボード compact イベント (配列形式)

```
[lat, lon, layer_code, subtype_code, severity, pref_prefix]
```

| Index | フィールド | 例 | 説明 |
|---|---|---|---|
| 0 | lat | 35.689 | 緯度 (3桁) |
| 1 | lon | 139.692 | 経度 (3桁) |
| 2 | layer | "c" | c=crime, t=traffic, d=disaster |
| 3 | subtype | "thef" | 4文字短縮コード |
| 4 | severity | 3 | 1-5 |
| 5 | pref | "東京" | 都道府県先頭2文字 |

---

## 5. リスクスコア計算

### 5-1. P(incident) — 適応メッシュ

```
density_score = min(1.0, count × area_factor / 100.0)
    area_factor = (0.0025 / grid_deg)²
severity_score = avg_severity / 5.0
night_factor = 1.0 + 0.2 × night_ratio
risk_score = min(1.0, (density × 0.6 + severity × 0.4) × night_factor)
```

### 5-2. P(escape) — Safe Haven近接度

```
distance_score:   0.1km=1.0, 0.3km=0.85, 0.5km=0.70, 1km=0.45, 2km=0.20
density_score:    min(1.0, havens_500m / 5.0)
proximity_score:  Σ(weight × (1 - dist/2km)) / 3.0, top 15 havens
arrival_score:    max(0, min(1, 1 - (arrival_min - 4) / 11))
night_penalty:    22-06時=0.65, 20-22時=0.85, else=1.0

P(escape) = (distance×0.35 + density×0.25 + proximity×0.20 + arrival×0.20) × night_penalty
```

Haven type weights:
| 施設 | 重み | 24H |
|---|---|---|
| 交番 | 1.00 | Yes |
| 消防署 | 0.90 | Yes |
| コンビニ | 0.85 | Yes |
| 病院 | 0.75-0.85 | Varies |
| 駅 | 0.70 | No |
| ファストフード24H | 0.60 | Yes |
| AED | 0.45 | Varies |

### 5-3. Expected Harm

```
Expected_Harm = P(incident) × (severity / 5) × (1 − P(escape))
```

---

## 6. ダッシュボード配信ファイル

| ファイル | サイズ | 内容 | 更新タイミング |
|---|---|---|---|
| events_compact.json | 11MB | 227,078件 (1/10サンプル) | バッチ再生成時 |
| grid_risk.json | 2.8MB | 10,000セル (EH+P_esc付き) | バッチ再生成時 |
| heat_crime.json | 15MB | 680,624点 | バッチ再生成時 |
| heat_traffic.json | 36MB | 1,589,944点 | バッチ再生成時 |
| heat_disaster.json | 8KB | 216点 | バッチ再生成時 |
| heat_weather.json | 4B | 0点 (未統合) | — |
| contour_matrix.json | 376KB | 221×321 Gaussian kernel | バッチ再生成時 |
| summary.json | 4KB | メタデータ | バッチ再生成時 |
| hotspots_expected_harm.json | ~20KB | Top 20 EHセル | バッチ再生成時 |
| escape_deficit.json | ~20KB | Top 20 低P(escape)セル | バッチ再生成時 |

---

## 7. スクリプト一覧

| スクリプト | 用途 | 入力 | 出力 |
|---|---|---|---|
| `download_pref_crime.py` | 22県犯罪CSV取得 | URLs | data/crime/prefectures/ |
| `download_pref_phase2.py` | NPA公式リンク経由取得 | NPA links | data/crime/prefectures/ |
| `download_historical_crime.py` | 2018-2023年分取得 | URLs | data/crime/prefectures/ |
| `normalize_crime.py` | 犯罪CSV正規化 | CSVs | crime_national.json |
| `normalize_traffic_full.py` | 交通事故全件正規化 | CSVs | traffic_collision_full.json |
| `integrate_full.py` | 全データ統合→ダッシュボード | normalized/ | dashboard/data/ |
| `build_adaptive_mesh.py` | 適応メッシュ生成 | normalized/ | adaptive_mesh.json |
| `build_estat_crime_full.py` | e-Stat犯罪統計解析 | estat_*.json | estat_crime_full.json |
| `generate_synthetic_events.py` | 合成イベント生成 | estat + centroids | synthetic_events.json |
| `task7_8_escape_harm.py` | P(escape)+EH計算 | grid + havens | grid_risk.json更新 |
| `fushinsha_crawler.py` | 不審者30分クローラー | URLs | fushinsha_live/ |
| `collect_new_sources.py` | NHK/Yahoo/河川収集 | RSS/URLs | realtime/ |
| `step3_risk_recalc.py` | リスクスコア再計算 | normalized/ | scored events |
| `prepare_map_data.py` | 旧ダッシュボード生成 | normalized/ | dashboard/data/ |

---

## 8. インフラ構成

### ローカル (現状)
- macOS + Python 3.9
- GitHub Pages (静的ダッシュボード)
- localhost:8888 (開発用)

### Cloudflare Workers (準備済み)
```
workers/
├── risk-space-mcp/     # MCPエンドポイント
│   ├── src/index.js    # get_risk_field, get_hotspots, get_signals, update_field
│   └── wrangler.toml   # R2 + KV binding
├── line-bot/           # LINE Bot
│   ├── src/index.js    # 位置情報→リスク分析, 帰路チェック, 通報
│   └── wrangler.toml   # KV binding + LINE secrets
├── deploy.sh           # 一括デプロイスクリプト
└── README.md           # セットアップ手順
```

| サービス | 用途 | 状態 |
|---|---|---|
| R2 | grid_risk.json等の格納 | コード準備済み |
| KV | リアルタイムキャッシュ (TTL 5min) | コード準備済み |
| Workers | MCPエンドポイント + LINE Bot | コード準備済み |
| GitHub Pages | 静的ダッシュボード | **稼働中** |

---

## 9. 未実装・次のステップ

| 優先度 | 項目 | 依存 |
|---|---|---|
| 🔴 | CF Workers + LINE Bot デプロイ | wrangler login + LINE token |
| 🔴 | 気象レイヤー統合 (アメダス+警報) | データは取得済み |
| 🟠 | Telegram公開チャンネル監視 | Bot token |
| 🟠 | 地価公示API統合 | reinfolib APIキー |
| 🟠 | 残り24県犯罪CSV (Selenium) | Playwright/Selenium |
| 🟡 | X(Twitter) Filtered Stream | API v2キー |
| 🟡 | 消防庁119統計 | e-Stat追加クエリ |
| 🟡 | 時空間KDE確率分布 | scipy |
| 🟢 | 曜日×時間帯ベイズモデル | pymc3 |
| 🟢 | 経年変化トレンド分析 | 十分なデータあり |
