# Risk Space MCP — 共通スキーマ仕様書

## 概要

犯罪・災害・交通事故・気象を統合した「リスク確率空間」のための共通スキーマ。
UK Police APIの「位置×カテゴリ×時間」モデルを日本版として実現する。

---

## スキーマ定義

```json
{
  "id": "string (UUID v4)",
  "source_id": "string | null",

  "layer": "string (enum)",
  "subtype": "string (enum)",

  "geometry": {
    "type": "Point",
    "coordinates": [139.6917, 35.6895]
  },
  "admin": {
    "prefecture": "string",
    "prefecture_code": "string (2桁)",
    "city": "string",
    "city_code": "string (5-6桁)",
    "town": "string | null"
  },
  "spatial_resolution": "string (enum)",

  "occurred_at": "string (ISO 8601)",
  "published_at": "string (ISO 8601) | null",
  "time_resolution": "string (enum)",
  "realtime": "boolean",

  "severity": "integer (1-5) | null",
  "risk_score": "number (0.0-1.0) | null",

  "source": {
    "org": "string",
    "url": "string",
    "license": "string",
    "fee": "boolean",
    "update_freq": "string (enum)",
    "missing_rate": "number (0.0-1.0)",
    "geocoded": "boolean"
  },

  "raw": "object"
}
```

---

## フィールド定義

### 識別フィールド

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string (UUID v4) | YES | システム生成の一意識別子 |
| `source_id` | string \| null | NO | 元データのID（気象庁の`eid`、警察庁の`本票番号`等） |

### レイヤー・分類

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `layer` | string (enum) | YES | リスクの大分類 |
| `subtype` | string (enum) | YES | リスクの小分類 |

#### `layer` 列挙値

| 値 | 説明 | 主なデータソース |
|---|---|---|
| `crime` | 犯罪 | 警視庁犯罪発生情報、e-Stat犯罪統計 |
| `disaster` | 自然災害 | 気象庁地震情報、台風情報 |
| `traffic` | 交通事故 | 警察庁交通事故統計 |
| `weather` | 気象 | 気象庁アメダス・警報・天気概況 |
| `evacuation` | 避難施設 | 国土地理院指定緊急避難場所 |

#### `subtype` 列挙値

| layer | subtype | 説明 | ソース |
|---|---|---|---|
| crime | `theft_purse_snatching` | ひったくり | 警視庁 |
| crime | `theft_vehicle` | 自動車盗 | 警視庁 |
| crime | `theft_motorcycle` | オートバイ盗 | 警視庁 |
| crime | `theft_bicycle` | 自転車盗 | 警視庁 |
| crime | `theft_car_parts` | 車上ねらい・部品ねらい | 警視庁 |
| crime | `theft_vending_machine` | 自動販売機ねらい | 警視庁 |
| crime | `crime_total` | 刑法犯認知件数（集計） | e-Stat |
| crime | `crime_violent` | 凶悪犯認知件数（集計） | e-Stat |
| crime | `crime_brutal` | 粗暴犯認知件数（集計） | e-Stat |
| crime | `crime_theft` | 窃盗犯認知件数（集計） | e-Stat |
| crime | `crime_intellectual` | 知能犯認知件数（集計） | e-Stat |
| crime | `crime_moral` | 風俗犯認知件数（集計） | e-Stat |
| disaster | `quake` | 地震 | 気象庁 |
| disaster | `typhoon` | 台風 | 気象庁 |
| disaster | `flood` | 洪水 | 気象庁警報 |
| disaster | `landslide` | 土砂災害 | 気象庁警報 |
| traffic | `collision` | 交通事故（衝突） | 警察庁 |
| traffic | `collision_fatal` | 死亡事故 | 警察庁（死者数>0） |
| traffic | `collision_injury` | 負傷事故 | 警察庁（負傷者数>0） |
| traffic | `collision_stats` | 交通事故発生件数（集計） | e-Stat |
| traffic | `collision_fatal_stats` | 交通事故死者数（集計） | e-Stat |
| traffic | `collision_injury_stats` | 交通事故負傷者数（集計） | e-Stat |
| weather | `observation` | 気象観測値 | アメダス |
| weather | `warning` | 警報 | 気象庁 |
| weather | `advisory` | 注意報 | 気象庁 |
| weather | `forecast` | 天気予報・概況 | 気象庁 |
| evacuation | `shelter` | 指定緊急避難場所 | 国土地理院 |

### 空間フィールド

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `geometry` | GeoJSON Point | NO* | 経度・緯度（WGS84, EPSG:4326）。coordinates は [lon, lat] 順。 |
| `admin.prefecture` | string | YES | 都道府県名 |
| `admin.prefecture_code` | string | YES | 都道府県コード（JIS X 0401, 2桁ゼロ埋め） |
| `admin.city` | string | NO | 市区町村名 |
| `admin.city_code` | string | NO | 市区町村コード（JIS X 0402, 5-6桁） |
| `admin.town` | string | NO | 町丁目名 |
| `spatial_resolution` | string (enum) | YES | 空間粒度 |

*`geometry` は座標が取得可能なソースでは必須。犯罪データ等、住所のみのソースでは null 許容（後工程でジオコーディング）。

#### `spatial_resolution` 列挙値

| 値 | 説明 | 精度 | 該当ソース |
|---|---|---|---|
| `point` | 座標点 | ~10m | 交通事故、地震震源、アメダス局 |
| `chome` | 町丁目 | ~100-500m | 警視庁犯罪 |
| `city` | 市区町村 | ~数km | 気象庁警報 |
| `prefecture` | 都道府県 | ~数十km | 天気概況、e-Stat統計 |
| `mesh_1km` | 1kmメッシュ | 1km | （将来用） |
| `mesh_500m` | 500mメッシュ | 500m | （将来用） |

### 時間フィールド

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `occurred_at` | string (ISO 8601) | YES | 事象の発生日時。タイムゾーンは `+09:00` (JST) |
| `published_at` | string (ISO 8601) \| null | NO | データの公表日時 |
| `time_resolution` | string (enum) | YES | 時間粒度 |
| `realtime` | boolean | YES | リアルタイムデータかどうか |

#### `time_resolution` 列挙値

| 値 | 説明 | 該当ソース |
|---|---|---|
| `second` | 秒 | 地震発生時刻 |
| `minute` | 分 | 交通事故発生時刻、アメダス更新 |
| `hour` | 時 | 警視庁犯罪（発生時） |
| `day` | 日 | — |
| `month` | 月 | — |
| `year` | 年 | e-Stat統計 |

### リスク評価フィールド

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `severity` | integer (1-5) \| null | NO | 重篤度（1=軽微, 5=致命的）。ソースのデータから変換。 |
| `risk_score` | number (0.0-1.0) \| null | NO | 正規化リスクスコア。複数シグナル重畳後に算出（後工程）。 |

#### `severity` マッピング基準

| severity | disaster (quake) | traffic | crime |
|---|---|---|---|
| 1 | 震度1-2 | 物損のみ | 窃盗（未遂） |
| 2 | 震度3 | 軽傷1名 | 窃盗（既遂・軽微） |
| 3 | 震度4-5弱 | 重傷または複数負傷 | ひったくり・車上ねらい |
| 4 | 震度5強-6弱 | 死亡1名 | 強盗・傷害 |
| 5 | 震度6強以上 | 死亡複数 | 殺人・放火 |

### ソースメタデータ

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `source.org` | string | YES | 提供組織名 |
| `source.url` | string | YES | 取得元URL |
| `source.license` | string | YES | ライセンス |
| `source.fee` | boolean | YES | 有料データか |
| `source.update_freq` | string (enum) | YES | 更新頻度 |
| `source.missing_rate` | number (0.0-1.0) | YES | 座標欠損率（0.0=欠損なし、1.0=全欠損） |
| `source.geocoded` | boolean | YES | 後工程でジオコーディングされたデータか否か |

#### `source.update_freq` 列挙値

| 値 | 説明 |
|---|---|
| `realtime` | リアルタイム（分単位） |
| `hourly` | 毎時 |
| `daily` | 日次 |
| `monthly` | 月次 |
| `yearly` | 年次 |
| `static` | 更新なし（避難場所等） |

### 生データ

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `raw` | object | YES | 元データをそのまま保持。フィールド名は元のまま。 |

---

## 実データへの適用例

### 気象庁 地震情報 → 共通スキーマ

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "source_id": "20260401100625",
  "layer": "disaster",
  "subtype": "quake",
  "geometry": {
    "type": "Point",
    "coordinates": [139.595, 36.062]
  },
  "admin": {
    "prefecture": "茨城県",
    "prefecture_code": "08",
    "city": null,
    "city_code": null,
    "town": null
  },
  "spatial_resolution": "point",
  "occurred_at": "2026-04-01T10:06:00+09:00",
  "published_at": "2026-04-01T11:15:00+09:00",
  "time_resolution": "second",
  "realtime": true,
  "severity": 3,
  "risk_score": null,
  "source": {
    "org": "気象庁",
    "url": "https://www.jma.go.jp/bosai/quake/data/list.json",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "realtime"
  },
  "raw": {
    "ctt": "20260401111505",
    "eid": "20260401100625",
    "rdt": "2026-04-01T11:15:00+09:00",
    "ttl": "顕著な地震の震源要素更新のお知らせ",
    "ift": "発表",
    "at": "2026-04-01T10:06:00+09:00",
    "anm": "茨城県南部",
    "acd": "301",
    "cod": "+3606.2+13959.5-48000/",
    "mag": "5.0",
    "maxi": ""
  }
}
```

### 警視庁 犯罪発生情報 → 共通スキーマ

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "source_id": null,
  "layer": "crime",
  "subtype": "theft_purse_snatching",
  "geometry": null,
  "admin": {
    "prefecture": "東京都",
    "prefecture_code": "13",
    "city": "千代田区",
    "city_code": "131016",
    "town": "有楽町１丁目"
  },
  "spatial_resolution": "chome",
  "occurred_at": "2024-11-08T17:00:00+09:00",
  "published_at": null,
  "time_resolution": "hour",
  "realtime": false,
  "severity": 3,
  "risk_score": null,
  "source": {
    "org": "警視庁",
    "url": "https://www.keishicho.metro.tokyo.lg.jp/about_mpd/jokyo_tokei/jokyo/hanzaihasseijyouhou.files/1_tokyo_2024hittakuri.csv",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "yearly"
  },
  "raw": {
    "罪名": "窃盗",
    "手口": "ひったくり",
    "管轄警察署": "丸の内",
    "管轄交番": "有楽町駅前",
    "市区町村コード": "131016",
    "都道府県": "東京都",
    "市区町村": "千代田区",
    "町丁目": "有楽町１丁目",
    "発生年月日": "20241108",
    "発生時": "17",
    "発生場所": "道路上",
    "被害者の性別": "女性",
    "被害者の年齢": "30歳代",
    "現金被害の有無": "あり"
  }
}
```

### 警察庁 交通事故 → 共通スキーマ

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "source_id": "10-059-0001",
  "layer": "traffic",
  "subtype": "collision_injury",
  "geometry": {
    "type": "Point",
    "coordinates": [141.3527, 43.1021]
  },
  "admin": {
    "prefecture": "北海道",
    "prefecture_code": "10",
    "city": null,
    "city_code": "103",
    "town": null
  },
  "spatial_resolution": "point",
  "occurred_at": "2023-12-27T15:42:00+09:00",
  "published_at": null,
  "time_resolution": "minute",
  "realtime": false,
  "severity": 2,
  "risk_score": null,
  "source": {
    "org": "警察庁",
    "url": "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/2024/honhyo_2024.csv",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "yearly"
  },
  "raw": {
    "資料区分": 1,
    "都道府県コード": 10,
    "警察署等コード": "059",
    "本票番号": "0001",
    "事故内容": 2,
    "死者数": 0,
    "負傷者数": 1,
    "地点_緯度": 430607590,
    "地点_経度": 1412109599,
    "天候": 2,
    "路面状態": 2,
    "事故類型": 21
  }
}
```

### 気象庁 アメダス → 共通スキーマ

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "source_id": "11001",
  "layer": "weather",
  "subtype": "observation",
  "geometry": null,
  "admin": {
    "prefecture": "北海道",
    "prefecture_code": "01",
    "city": null,
    "city_code": null,
    "town": null
  },
  "spatial_resolution": "point",
  "occurred_at": "2026-04-01T21:00:00+09:00",
  "published_at": "2026-04-01T21:00:00+09:00",
  "time_resolution": "minute",
  "realtime": true,
  "severity": null,
  "risk_score": null,
  "source": {
    "org": "気象庁",
    "url": "https://www.jma.go.jp/bosai/amedas/data/map/20260401210000.json",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "realtime"
  },
  "raw": {
    "station_id": "11001",
    "temp": [3.2, 0],
    "humidity": [57, 0],
    "precipitation1h": [0.0, 0],
    "windSpeed": [3.5, 0],
    "windDirection": [7, 0]
  }
}
```

### e-Stat 犯罪統計 → 共通スキーマ

```json
{
  "id": "e5f6a7b8-c9d0-1234-efab-345678901234",
  "source_id": "0000010111_K4201_13000_2023100000",
  "layer": "crime",
  "subtype": "crime_total",
  "geometry": null,
  "admin": {
    "prefecture": "東京都",
    "prefecture_code": "13",
    "city": null,
    "city_code": null,
    "town": null
  },
  "spatial_resolution": "prefecture",
  "occurred_at": "2023-04-01T00:00:00+09:00",
  "published_at": null,
  "time_resolution": "year",
  "realtime": false,
  "severity": null,
  "risk_score": null,
  "source": {
    "org": "総務省統計局 / 警察庁",
    "url": "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData?statsDataId=0000010111",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "yearly"
  },
  "raw": {
    "@tab": "00001",
    "@cat01": "K4201",
    "@area": "13000",
    "@time": "2023100000",
    "@unit": "件",
    "$": "89098"
  }
}
```

### 気象庁 警報 → 共通スキーマ

```json
{
  "id": "d4e5f6a7-b8c9-0123-defa-234567890123",
  "source_id": null,
  "layer": "weather",
  "subtype": "warning",
  "geometry": null,
  "admin": {
    "prefecture": "北海道",
    "prefecture_code": "01",
    "city": null,
    "city_code": "011000",
    "town": null
  },
  "spatial_resolution": "city",
  "occurred_at": "2026-04-01T15:22:00+09:00",
  "published_at": "2026-04-01T15:22:00+09:00",
  "time_resolution": "minute",
  "realtime": true,
  "severity": 3,
  "risk_score": null,
  "source": {
    "org": "気象庁",
    "url": "https://www.jma.go.jp/bosai/warning/data/warning/map.json",
    "license": "政府標準利用規約",
    "fee": false,
    "update_freq": "realtime"
  },
  "raw": {
    "warning_code": "20",
    "status": "発表",
    "area_code": "011000"
  }
}
```

---

## MCP ツール設計との対応

| ツール | 使用フィールド |
|---|---|
| `get_risk_field(lat, lon, radius_km, time, layers)` | `geometry`, `occurred_at`, `layer`, `risk_score` |
| `get_hotspots(prefecture, layer, date_range)` | `admin.prefecture`, `layer`, `occurred_at`, 集計 |
| `get_signals(lat, lon, radius_km, time_window)` | `geometry`, `occurred_at`, `raw` |
| `update_field(event_type, lat, lon, timestamp, severity)` | 全フィールド（新規レコード作成） |

---

## インデックス設計（参考）

R2/D1 実装時の推奨インデックス:

1. **空間インデックス**: `geometry` → Geohash または S2 Cell ID でプレフィックス検索
2. **時間インデックス**: `occurred_at` → パーティション（年月日）
3. **複合インデックス**: `layer` + `admin.prefecture_code` + `occurred_at`
4. **リスクインデックス**: `risk_score` DESC（ホットスポット検索用）
