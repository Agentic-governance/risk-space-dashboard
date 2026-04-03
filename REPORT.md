# Risk Space MCP — プロジェクト仕様書 v2

**最終更新**: 2026-04-03
**ダッシュボード**: https://agentic-governance.github.io/risk-space-dashboard/
**リポジトリ**: https://github.com/Agentic-governance/risk-space-dashboard

---

## 1. 概要

日本全国の犯罪・交通事故・災害・気象を統合した**リスク確率空間**を構築するプロジェクト。
UK Police APIの「位置×カテゴリ×時間」モデルの日本版として、MCPツール経由でAIエージェントにリスク情報を提供する。

### データ規模

| レイヤー | イベント数 | 期間 | ソース |
|---|---|---|---|
| crime（犯罪） | **680,624** | 2018-2024 | 22都道府県警CSV + 25都道府県e-Stat合成 |
| traffic（交通事故） | **1,589,944** | 2019-2024 | 警察庁オープンデータ全件 |
| disaster（地震） | **216** | 2024 | 気象庁地震情報 |
| **合計** | **2,270,784** | 2018-2024 | |

---

## 2. データソース詳細

### 2-1. 犯罪データ（680,624件）

#### 個別イベント（22都道府県, 492 CSVファイル, 461,867件）

NPA統一フォーマット「窃盗7手口」:
- ひったくり、車上ねらい、部品ねらい、自販機ねらい、自動車盗、オートバイ盗、自転車盗

| 都道府県 | 件数 | 年度 |
|---|---|---|
| 大阪府 | ~234,000 | 2018-2024 |
| 神奈川県 | ~101,000 | 2018-2024 |
| 愛知県 | ~70,000 | 2019-2024 |
| 兵庫県 | ~76,000 | 2018-2024 |
| 埼玉県 | ~20,000 | 2024 |
| 千葉県 | ~14,000 | 2024 |
| 福岡県 | ~12,000 | 2024 |
| 宮城県 | ~17,000 | 2018-2024 |
| 静岡県 | ~8,000 | 2022-2024 |
| 長野県 | ~10,000 | 2018-2024 |
| その他12県 | ~20,000 | 各県1-3年分 |

**東京都**: 29,043件（2024）、28,936件ジオコーディング済み（国土地理院API, 99.6%成功率）

#### e-Stat合成イベント（25都道府県, 189,821件）
- CSV未取得の25都道府県について、e-Stat犯罪統計（703,351件/年）から人口按分で市区町村に配置
- 全犯罪種別: 凶悪犯(5,750) + 粗暴犯(58,474) + 窃盗犯(483,695) + 知能犯(50,035) + 風俗犯(11,774) + その他(93,623)

### 2-2. 交通事故（1,589,944件）

| 年度 | 件数 | ソース |
|---|---|---|
| 2019 | 381,237 | 警察庁 honhyo_2019.csv |
| 2020 | 309,178 | 警察庁 honhyo_2020.csv |
| 2021 | N/A | NPA未公開（404） |
| 2022 | 300,839 | 警察庁 honhyo_2022.csv |
| 2023 | 307,930 | 警察庁 honhyo_2023.csv |
| 2024 | 290,895 | 警察庁 honhyo_2024.csv |

- 座標変換: 度分秒×1000 → WGS84（100%成功）
- subtype: collision, collision_injury, collision_fatal

### 2-3. 地震（216件）

- ソース: 気象庁 地震情報API
- 座標: ISO 6709 codフィールド解析（216/244件成功, 88.5%）

### 2-4. リアルタイム不審者情報（31件）

- ソース: JASPIC nordot.appフィード + 都道府県警サイト
- 種別: 37カテゴリ（声かけ、つきまとい、痴漢、クマ出没等）
- クローラー: `scripts/fushinsha_crawler.py`（30分間隔, `--loop`オプション）
- 47都道府県URLマスター: `data/realtime/source_map.json`

---

## 3. ジオコーディング方式

| データ | 方法 | 精度 |
|---|---|---|
| 東京都犯罪 | 国土地理院 msearch API（全件） | 町丁目レベル |
| 22都道府県犯罪 | 市区町村重心座標（893市区町村, 887成功） | 市区町村レベル + jitter |
| 交通事故 | 度分秒×1000 → WGS84 | 地点レベル |
| 地震 | ISO 6709 cod解析 | 震源レベル |
| 合成イベント | 人口按分 + 都市重心 | 市区町村レベル |

---

## 4. ダッシュボード仕様

### スタック
- **Leaflet.js 1.9.4** — 地図表示
- **Leaflet.heat** — ヒートマップ
- **D3.js 7.8.5** — 等高線（d3-contour）
- **Chart.js 4.4.1** — 時間帯別チャート
- **GitHub Pages** — ホスティング

### 表示モード
| モード | 説明 |
|---|---|
| ヒートマップ | レイヤー別グラデーション表示 |
| 等高線 | 0.1°グリッド Gaussian kernel (σ=0.3°) |
| 両方 | ヒート+等高線重畳 |
| ポイント | 個別イベントマーカー（最大8,000点サンプル） |

### レイヤー切替
- 全体（crime + traffic + disaster 動的マージ）
- 犯罪のみ（680,624点）
- 交通のみ（1,589,944点）
- 災害のみ（216点）

### リスク解説パネル（右側）
- 地図クリックで最寄りグリッドセルのリスク分析を表示
- レイヤー別内訳、主要subtype、年間平均件数
- 時間帯別チャート（24時間ヒストグラム）
- 近隣イベント一覧

### データファイル

| ファイル | サイズ | 内容 |
|---|---|---|
| events_compact.json | 11MB | 227,078件（1/10サンプル, 配列形式） |
| heat_crime.json | 15MB | 犯罪ヒートマップ点群 |
| heat_traffic.json | 36MB | 交通事故ヒートマップ点群 |
| heat_disaster.json | 8KB | 地震ヒートマップ点群 |
| grid_risk.json | 5.3MB | 8,336グリッドセル（0.05°≒5km） |
| contour_matrix.json | 376KB | 221×321等高線マトリクス |
| summary.json | 4KB | メタデータ |

---

## 5. グリッドリスクスコア計算

```
density_score = min(1.0, count / 200.0)   # 200件で飽和（複数年対応）
severity_score = avg_severity / 5.0
risk_score = density_score × 0.6 + severity_score × 0.4
```

- グリッド解像度: 0.05°（約5km）
- 8,336セル（count ≥ 3のみ）
- 年次平均件数（annual_avg）算出済み
- カバー年数（years_covered）付き

---

## 6. 不審者情報クローラー

### JASPICベンチマーク
- JASPIC: 47都道府県の不審者情報を人力収集・nordot配信
- 37種別の分類体系を解析済み

### 我々のクローラーの優位性
1. **30分間隔自動クロール**（JASPICは人力・不定期）
2. **一次ソース直接アクセス**（JASPIC依存なし）
3. **severity (1-5)**（JASPICにない定量指標）
4. **geometry対応**（住所→座標変換パイプライン）
5. **risk_score**（他レイヤーとの統合リスク）
6. **動物リスク統合**（クマ・イノシシをdisasterレイヤーに）
7. **ハッシュベース重複排除**（増分クロール）

### 種別マッピング（抜粋）

| JASPICの種別 | subtype | severity | layer |
|---|---|---|---|
| 声かけ | suspicious_person_approach | 2 | crime |
| つきまとい | suspicious_person_stalking | 3 | crime |
| 痴漢 | sexual_crime_groping | 4 | crime |
| 強盗 | robbery | 5 | crime |
| 刃物所持 | weapons | 4 | crime |
| クマ出没 | wildlife_bear | 4 | disaster |
| イノシシ出没 | wildlife_boar | 3 | disaster |

---

## 7. MCPツール設計

### エンドポイント

| ツール | 引数 | 返却 |
|---|---|---|
| get_signals | lat, lon, radius_km, time_window, layers[] | イベント一覧 |
| get_hotspots | prefecture, layer, date_from, date_to | ホットスポット |
| get_risk_field | lat, lon, radius_km, layers[] | リスクスコア+内訳 |
| get_risk_timeline | lat, lon, radius_km, period_days | 日別リスク推移 |
| update_field | event_type, lat, lon, severity | ユーザー通報 |

### インフラ構成
- **Cloudflare Workers**: MCPエンドポイント・リスク計算
- **R2**: 正規化JSON格納（2.27M件）
- **KV**: リアルタイムキャッシュ（気象60秒、不審者3600秒）
- **D1**: Geohash空間インデックス

---

## 8. ファイル構成

```
risk_space/
├── dashboard/
│   ├── index.html          # ダッシュボード本体
│   └── data/               # 前処理済みデータ
├── docs/                   # GitHub Pages用コピー
├── data/
│   ├── crime/
│   │   ├── prefectures/    # 22都道府県CSV (492ファイル)
│   │   └── national/       # e-Stat統計・合成イベント・重心座標
│   ├── normalized/         # 正規化済みJSON
│   ├── geocoded/           # ジオコーディング結果
│   ├── traffic/            # 交通事故CSV (2019-2024)
│   └── realtime/           # 不審者情報・ニュース
├── scripts/
│   ├── prepare_map_data.py     # ダッシュボードデータ生成
│   ├── integrate_full.py       # 全データ統合 (2.27M件)
│   ├── fushinsha_crawler.py    # 不審者情報30分クローラー
│   ├── normalize_crime.py      # 犯罪CSV正規化
│   ├── normalize_traffic_full.py # 交通事故全件正規化
│   └── step3_risk_recalc.py    # リスクスコア再計算
├── schema.md               # データスキーマ仕様
├── sources.json            # 15データソース一覧
├── mcp_design.md           # MCPツール設計書
└── REPORT.md               # 本ファイル
```

---

## 9. 次のステップ

### 即座に実行可能
- [ ] Cloudflare Workers + R2デプロイ（MCPエンドポイント）
- [ ] 不審者クローラー常時稼働（`--loop`モード、cronまたはWorker）
- [ ] 気象庁リアルタイムAPI統合（地震60秒、アメダス10分）

### データ拡充
- [ ] 残り24都道府県の犯罪CSV取得（Selenium/Playwright対応）
- [ ] 2021年交通事故データ（NPA問合せ）
- [ ] 過去の地震データ（気象庁過去震度データベース）
- [ ] 避難場所データのダッシュボード統合

### 確率モデル
- [ ] 時空間カーネル密度推定（KDE）による確率分布
- [ ] 曜日×時間帯×季節のベイズモデル
- [ ] 経年変化トレンド分析（2018→2024の増減）

---

## 10. ライセンス

| データ | ライセンス | 再配布 |
|---|---|---|
| 警察庁・都道府県警CSV | 政府標準利用規約（CC BY互換） | 出典明記でOK |
| e-Stat統計 | 政府標準利用規約 | 出典明記でOK |
| 気象庁データ | 政府標準利用規約 | 出典明記でOK |
| JASPIC nordot | 報道利用 | 注意が必要 |
| ガッコム安全ナビ | スクレイピング | robots.txt要確認 |
