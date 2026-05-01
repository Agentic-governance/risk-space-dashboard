# historical data

- `earthquakes_2021_2025.json`: USGS地震イベント。更新頻度: 週次。
- `traffic_accidents_2020_2024.json`: NPA交通事故統計。更新頻度: 週次。
- `crime_monthly_series.json`: NPA/e-Stat月次犯罪系列(2019-2025)。更新頻度: 月次。
- `fushinsha_1year.json`: news.jp不審者ユニット記事(過去1年)。更新頻度: 週次。
- `weather_monthly_2025.json`: JMA AMeDAS月別平均気温/降水量(2025)。更新頻度: 月次。
- `police_archives.json`: 各警察サイトのアーカイブ/バックナンバー候補URL。更新頻度: 月次。
- `jma_weather_5yr.json`: JMA過去5年の月別統計。更新頻度: 月次。

共通フォーマット:
- UTF-8 JSON
- `generated_at` (UTC ISO8601) を含む
- 欠損値は `null` を許容
