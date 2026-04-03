# Risk Space MCP

犯罪・災害・交通事故・気象を統合した「リスク確率空間MCP」の基盤スキーマプロジェクト。

## 構成

- `schema.md` — 確定スキーマ仕様書
- `field_map.md` — フィールドマッピング表
- `sources.json` — データソース一覧・取得ステータス
- `issues.md` — 問題点・注意事項
- `data/` — 取得した生データ

## 設計思想

- 確率分布としてのリスク表現（確定的ではない）
- UK Police API「位置×カテゴリ×時間」の日本版
- Patent Space MCP / Caselaw MCPと同じアーキテクチャ（Cloudflare Workers + R2）
