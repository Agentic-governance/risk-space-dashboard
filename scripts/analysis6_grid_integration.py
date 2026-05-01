import json
from pathlib import Path

grid_path = Path('dashboard/data/grid_risk.json')
if not grid_path.exists():
    grid_path = Path('docs/data/grid_risk.json')
if not grid_path.exists():
    print('grid_risk.json なし'); exit()

with open(grid_path, encoding='utf-8') as f:
    grid = json.load(f)
print(f'グリッドセル数: {len(grid)}')

# エスカレーション
escalation_lookup = {}
esc_path = Path('data/analysis/escalation/escalation_alerts.json')
if esc_path.exists():
    with open(esc_path, encoding='utf-8') as f:
        alerts = json.load(f)
    for a in alerts:
        key = f"{round(a['lat'],2)}_{round(a['lon'],2)}"
        escalation_lookup[key] = a
    print(f'エスカレーション: {len(alerts)}地点')

# クラスター
cluster_path = Path('data/analysis/modus/cluster_profiles.json')
clusters = []
if cluster_path.exists():
    with open(cluster_path, encoding='utf-8') as f:
        clusters = json.load(f)
    print(f'クラスター: {len(clusters)}個')

# 共起ルール
rules_path = Path('data/analysis/cooccurrence/association_rules.json')
rules = []
if rules_path.exists():
    with open(rules_path, encoding='utf-8') as f:
        rules = json.load(f)
    print(f'共起ルール: {len(rules)}件')

# 被害者経路
pathway_path = Path('data/analysis/victim_pathway/pathway_analysis.json')
pathways = {}
if pathway_path.exists():
    with open(pathway_path, encoding='utf-8') as f:
        pathways = json.load(f)
    print(f'被害者経路プロファイル: {len(pathways)}種')

# 交通事故
traffic_path = Path('data/analysis/traffic_profiles/compound_risk_factors.json')
traffic_risks = {}
if traffic_path.exists():
    with open(traffic_path, encoding='utf-8') as f:
        traffic_risks = json.load(f)
    print(f'交通リスク因子: {len(traffic_risks.get("single_factor_risks",{}))}件')

# グリッドに反映
enriched_esc = 0
for cell in grid:
    lat = round(cell.get('lat',0), 2)
    lon = round(cell.get('lon',0), 2)
    key = f'{lat}_{lon}'

    # エスカレーション
    if key in escalation_lookup:
        a = escalation_lookup[key]
        cell['escalation'] = {
            'is_escalating': True,
            'corr': a['spearman_corr'],
            'severity_increase_pct': round(a['severity_increase']*100, 1),
            'recent_crimes': a.get('crime_sequence',[])[-3:],
        }
        enriched_esc += 1

    # アーキタイプ
    subtypes = cell.get('subtypes', {})
    if subtypes:
        dominant = max(subtypes, key=subtypes.get)
        cell['dominant_subtype'] = dominant
        if any(kw in dominant for kw in ['sexual','groping','voyeurism']): cell['archetype'] = '女性ターゲット型'
        elif any(kw in dominant for kw in ['approach','stalking']): cell['archetype'] = '接触犯型'
        elif any(kw in dominant for kw in ['theft','burglary']): cell['archetype'] = '財物犯型'
        elif 'collision_fatal' in dominant: cell['archetype'] = '重篤交通型'
        elif 'collision' in dominant: cell['archetype'] = '交通事故型'
        else: cell['archetype'] = '複合型'

# 統合メタデータ
meta = {
    'analysis_version': '2.0_structural',
    'escalation_alerts': len(escalation_lookup),
    'cluster_count': len(clusters),
    'cooccurrence_rules': len(rules),
    'pathway_profiles': len(pathways),
    'traffic_factors': len(traffic_risks.get('single_factor_risks',{})),
    'enriched_escalation_cells': enriched_esc,
}

# 保存
out = {'metadata': meta, 'grid': grid, 'cluster_profiles': clusters, 'top_cooccurrence_rules': rules[:30], 'victim_pathways': pathways, 'traffic_compound_risks': traffic_risks.get('compound_risks',[])[:20]}

out_path = Path('dashboard/data/grid_risk_enriched.json')
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
print(f'\n統合完了: {out_path}')
print(f'  エスカレーション付与: {enriched_esc}セル')
print(f'  アーキタイプ付与: {sum(1 for c in grid if "archetype" in c)}セル')

# docs/dataにもコピー
import shutil
docs_out = Path('docs/data/grid_risk_enriched.json')
shutil.copy(out_path, docs_out)
print(f'  コピー: {docs_out}')
