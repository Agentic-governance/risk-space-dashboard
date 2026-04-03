# Field Mapping — Risk Space MCP

各データソースのフィールドから共通スキーマへのマッピング表。

---

## 気象庁 地震情報

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| `eid` | `source_id` | そのまま |
| — | `layer` | 固定値 `"disaster"` |
| — | `subtype` | 固定値 `"quake"` |
| `cod` | `geometry.coordinates` | ISO 6709パース: `+DDMM.M+DDDMM.M-DDDDD/` → `[lon, lat]` に変換。例: `+3606.2+13959.5` → `[139.595+5/60, 36.0+62/600]` → `[139.9917, 36.1033]` |
| `anm` | `admin.prefecture` | 地域名から都道府県を抽出（「茨城県南部」→「茨城県」） |
| `acd` | `admin.city_code` | 気象庁独自の地域コード。JIS市区町村コードへの変換テーブル必要 |
| `at` | `occurred_at` | ISO 8601そのまま |
| `rdt` | `published_at` | ISO 8601そのまま |
| `mag` | `raw.mag` | 文字列→数値変換 |
| `maxi` | `severity` | 震度→severity変換: 1-2→1, 3→2, 4-5弱→3, 5強-6弱→4, 6強以上→5 |
| — | `time_resolution` | 固定値 `"second"` |
| — | `realtime` | 固定値 `true` |
| — | `spatial_resolution` | 固定値 `"point"` |
| 元レコード全体 | `raw` | JSONそのまま保持 |

---

## 気象庁 警報・注意報

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| — | `source_id` | null |
| — | `layer` | 固定値 `"weather"` |
| `warnings[].code` | `subtype` | コード変換: 警報コード→`"warning"` / `"advisory"` |
| — | `geometry` | null（市区町村コードから重心座標を取得可能だが後工程） |
| `areas[].code` | `admin.city_code` | そのまま（気象庁エリアコード。6-7桁） |
| `areas[].code` | `admin.prefecture_code` | 先頭2桁を抽出 |
| `reportDatetime` | `occurred_at` | ISO 8601そのまま |
| `reportDatetime` | `published_at` | 同上 |
| `warnings[].code` | `severity` | 警報=4, 注意報=2 として概算 |
| — | `time_resolution` | 固定値 `"minute"` |
| — | `realtime` | 固定値 `true` |
| — | `spatial_resolution` | 固定値 `"city"` |
| 元レコード | `raw` | JSONそのまま保持 |

### 警報コード（主要なもの）

| コード | 名称 | subtype |
|---|---|---|
| 02 | 暴風警報 | warning |
| 03 | 暴風雪警報 | warning |
| 04 | 大雨警報 | warning |
| 05 | 大雪警報 | warning |
| 10 | 大雨注意報 | advisory |
| 12 | 大雪注意報 | advisory |
| 13 | 風雪注意報 | advisory |
| 14 | 雷注意報 | advisory |
| 16 | 波浪注意報 | advisory |
| 20 | 暴風雪警報 | warning |
| 22 | 大雪警報 | warning |

---

## 気象庁 アメダス観測値

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| station_id (JSONキー) | `source_id` | そのまま |
| — | `layer` | 固定値 `"weather"` |
| — | `subtype` | 固定値 `"observation"` |
| — | `geometry` | アメダス局テーブル（amedastable.json）から座標取得 |
| — | `admin.prefecture_code` | アメダス局テーブルから取得 |
| タイムスタンプ（URLパラメータ） | `occurred_at` | URLの`{YYYYMMDDHHmmss}`をISO 8601に変換 |
| `temp[0]` | `raw.temp` | 値部分（[0]）を抽出。[1]は品質フラグ |
| `humidity[0]` | `raw.humidity` | 同上 |
| `precipitation1h[0]` | `raw.precipitation1h` | 同上 |
| `windSpeed[0]` | `raw.windSpeed` | 同上 |
| `windDirection[0]` | `raw.windDirection` | 16方位コード（0=静穏, 1=北北東, ... 16=北） |
| — | `severity` | 降水量・風速・気温から算出（閾値ベース） |
| — | `time_resolution` | 固定値 `"minute"` |
| — | `realtime` | 固定値 `true` |
| — | `spatial_resolution` | 固定値 `"point"` |
| 元レコード全体 | `raw` | JSONそのまま保持 |

### アメダス品質フラグ

| 値 | 意味 |
|---|---|
| 0 | 正常値 |
| 1 | 準正常値 |
| 2 | 疑問値 |
| null | データなし |

---

## 警視庁 犯罪発生情報

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| — | `source_id` | null（元データにIDなし） |
| — | `layer` | 固定値 `"crime"` |
| `手口` | `subtype` | 変換テーブル: ひったくり→`theft_purse_snatching`, 自転車盗→`theft_bicycle`, 車上ねらい→`theft_car_parts`, 部品ねらい→`theft_car_parts`, 自動販売機ねらい→`theft_vending_machine`, 自動車盗→`theft_vehicle`, オートバイ盗→`theft_motorcycle` |
| — | `geometry` | null（後工程でジオコーディング） |
| `都道府県（発生地）` | `admin.prefecture` | そのまま |
| `市区町村コード（発生地）` | `admin.city_code` | そのまま |
| `市区町村（発生地）` | `admin.city` | そのまま |
| `町丁目（発生地）` | `admin.town` | そのまま |
| `発生年月日（始期）` | `occurred_at` | `YYYYMMDD` + `発生時` → ISO 8601。例: `20241108` + `17` → `2024-11-08T17:00:00+09:00` |
| — | `published_at` | null |
| — | `severity` | subtype に基づく: ひったくり→3, 自動車盗→3, その他窃盗→2 |
| — | `time_resolution` | 固定値 `"hour"` |
| — | `realtime` | 固定値 `false` |
| — | `spatial_resolution` | 固定値 `"chome"` |
| 元行全体 | `raw` | CSVの全フィールドをオブジェクト化 |

### 手口→subtype 変換テーブル

| 手口（元データ） | subtype |
|---|---|
| ひったくり | `theft_purse_snatching` |
| 車上ねらい | `theft_car_parts` |
| 部品ねらい | `theft_car_parts` |
| 自動販売機ねらい | `theft_vending_machine` |
| 自動車盗 | `theft_vehicle` |
| オートバイ盗 | `theft_motorcycle` |
| 自転車盗 | `theft_bicycle` |

---

## 警察庁 交通事故統計

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| `都道府県コード`-`警察署等コード`-`本票番号` | `source_id` | ハイフン連結 |
| — | `layer` | 固定値 `"traffic"` |
| `死者数` | `subtype` | 死者数>0→`collision_fatal`, 負傷者数>0→`collision_injury`, それ以外→`collision` |
| `地点　緯度（北緯）` + `地点　経度（東経）` | `geometry.coordinates` | 度分秒×1000形式→10進度変換。`430607590` → `43 + 06/60 + 07.590/3600` = `43.10211°`。coordinates=[lon, lat] |
| `都道府県コード` | `admin.prefecture_code` | 2桁ゼロ埋め |
| `市区町村コード` | `admin.city_code` | そのまま |
| `発生日時　年`+`月`+`日`+`時`+`分` | `occurred_at` | 各フィールド結合→ISO 8601。例: 2023+12+27+15+42 → `2023-12-27T15:42:00+09:00` |
| — | `published_at` | null |
| `死者数` + `負傷者数` | `severity` | 死者複数→5, 死者1→4, 重傷→3, 軽傷→2, 物損→1 |
| — | `time_resolution` | 固定値 `"minute"` |
| — | `realtime` | 固定値 `false` |
| — | `spatial_resolution` | 固定値 `"point"` |
| 元行全体 | `raw` | CSVの全68フィールドをオブジェクト化（コード値のまま） |

### 座標変換処理の詳細

```
入力: 430607590 (緯度), 1412109599 (経度)

緯度:
  度 = 43
  分 = 06
  秒 = 07.590
  10進 = 43 + 6/60 + 7.590/3600 = 43.10211°

経度:
  度 = 141
  分 = 21
  秒 = 09.599
  10進 = 141 + 21/60 + 9.599/3600 = 141.35267°

出力: coordinates = [141.35267, 43.10211]
```

パースルール:
- 緯度（9桁）: `DDMMSSMMM` → D=先頭2桁, M=次2桁, S.mmm=残り5桁÷1000
- 経度（10桁）: `DDDMMSSMMM` → D=先頭3桁, M=次2桁, S.mmm=残り5桁÷1000

---

## 気象庁 天気概況

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| — | `source_id` | null |
| — | `layer` | 固定値 `"weather"` |
| — | `subtype` | 固定値 `"forecast"` |
| — | `geometry` | null（都道府県レベル） |
| `targetArea` | `admin.prefecture` | そのまま |
| URLパラメータ `{prefcode}` | `admin.prefecture_code` | 先頭2桁（130000→13） |
| `reportDatetime` | `occurred_at` | ISO 8601そのまま |
| `reportDatetime` | `published_at` | 同上 |
| `headlineText` + `text` | `raw` | テキストとして保持 |
| — | `severity` | null（テキスト解析が必要な場合は後工程） |
| — | `time_resolution` | 固定値 `"hour"` |
| — | `realtime` | 固定値 `true` |
| — | `spatial_resolution` | 固定値 `"prefecture"` |

---

## e-Stat 犯罪・交通事故統計

| 元フィールド | 共通スキーマ | 変換処理 |
|---|---|---|
| — | `source_id` | `{statsDataId}_{cat01}_{area}_{time}` を生成 |
| — | `layer` | K42xx → `"crime"`, K31xx → `"traffic"` |
| `@cat01` | `subtype` | K4201→`crime_total`, K420101→`crime_violent`, K420102→`crime_brutal`, K420103→`crime_theft`, K3101→`collision_stats`, K3103→`collision_fatal_stats` |
| — | `geometry` | null（都道府県レベルのため座標なし。重心座標は別途付与可能） |
| `@area` | `admin.prefecture_code` | e-Stat形式→JIS変換: "13000"→"13", "01000"→"01" |
| `@area` | `admin.prefecture` | コード→名称変換テーブル使用 |
| `@time` | `occurred_at` | "2023100000"→"2023-04-01T00:00:00+09:00"（年度開始日） |
| `$` | `raw.value` | 文字列→数値変換 |
| `@unit` | `raw.unit` | そのまま |
| — | `severity` | null（集計統計のためイベント単位ではない） |
| — | `time_resolution` | 固定値 `"year"` |
| — | `realtime` | 固定値 `false` |
| — | `spatial_resolution` | 固定値 `"prefecture"` |
| 元レコード全体 | `raw` | JSONそのまま保持 |

### e-Stat カテゴリコード→subtype 変換テーブル

| カテゴリコード | カテゴリ名 | subtype |
|---|---|---|
| K4201 | 刑法犯認知件数 | `crime_total` |
| K420101 | 凶悪犯認知件数 | `crime_violent` |
| K420102 | 粗暴犯認知件数 | `crime_brutal` |
| K420103 | 窃盗犯認知件数 | `crime_theft` |
| K420104 | 知能犯認知件数 | `crime_intellectual` |
| K420105 | 風俗犯認知件数 | `crime_moral` |
| K3101 | 交通事故発生件数 | `collision_stats` |
| K3103 | 交通事故死者数 | `collision_fatal_stats` |
| K3104 | 交通事故負傷者数 | `collision_injury_stats` |

### e-Stat 都道府県コード変換

| e-Stat area | JIS prefecture_code | 都道府県名 |
|---|---|---|
| 00000 | — | 全国 |
| 01000 | 01 | 北海道 |
| 13000 | 13 | 東京都 |
| 14000 | 14 | 神奈川県 |
| 23000 | 23 | 愛知県 |
| 27000 | 27 | 大阪府 |
| 40000 | 40 | 福岡県 |
| ... | ... | ... |

変換ルール: `area[:2]` で先頭2桁を取得（"13000"→"13"）

---

## 避難場所（G空間情報センター経由）

| 元フィールド（推定） | 共通スキーマ | 変換処理 |
|---|---|---|
| 施設ID | `source_id` | そのまま |
| — | `layer` | 固定値 `"evacuation"` |
| — | `subtype` | 固定値 `"shelter"` |
| 緯度 + 経度 | `geometry.coordinates` | [経度, 緯度] に変換 |
| 都道府県名 | `admin.prefecture` | そのまま |
| 市区町村名 | `admin.city` | そのまま |
| 施設名/住所 | `admin.town` | 該当部分を抽出 |
| — | `occurred_at` | null（静的データ。作成日を使用） |
| 洪水/地震/火災等のフラグ | `raw` | 災害種別フラグとして保持 |
| — | `severity` | null |
| — | `time_resolution` | null |
| — | `realtime` | 固定値 `false` |
| — | `spatial_resolution` | 固定値 `"point"` |

---

## 変換処理の共通ユーティリティ（実装メモ）

### 1. ISO 6709 座標パーサー

```python
def parse_iso6709(cod: str) -> tuple[float, float, float]:
    """'+DDMM.M+DDDMM.M-DDDDD/' → (lat, lon, depth_m)"""
    import re
    m = re.match(r'([+-]\d{4}\.\d+)([+-]\d{5}\.\d+)([+-]\d+)/', cod)
    lat_raw, lon_raw, depth = m.groups()
    lat = int(lat_raw[:3]) + float(lat_raw[3:]) / 60
    lon = int(lon_raw[:4]) + float(lon_raw[4:]) / 60
    return (lat, lon, int(depth))
```

### 2. NPA座標変換

```python
def parse_npa_coord(lat_raw: int, lon_raw: int) -> tuple[float, float]:
    """430607590, 1412109599 → (43.10211, 141.35267)"""
    lat_s = str(lat_raw).zfill(9)
    lat = int(lat_s[:2]) + int(lat_s[2:4])/60 + int(lat_s[4:])/1000/3600
    lon_s = str(lon_raw).zfill(10)
    lon = int(lon_s[:3]) + int(lon_s[3:5])/60 + int(lon_s[5:])/1000/3600
    return (lat, lon)
```

### 3. 犯罪発生日時パーサー

```python
def parse_keishicho_datetime(date_str: str, hour_str: str) -> str:
    """'20241108', '17' → '2024-11-08T17:00:00+09:00'"""
    y, m, d = date_str[:4], date_str[4:6], date_str[6:8]
    h = hour_str.zfill(2)
    return f"{y}-{m}-{d}T{h}:00:00+09:00"
```
