#!/usr/bin/env python3
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

try:
    import osmnx as ox
except Exception:
    ox = None

SCHOOL_PATH = Path('data/analysis/school_risk_v2/school_profiles_v2.json')
GRID_PATH = Path('dashboard/data/grid_risk.json')
INTERACTION_PATH = Path('data/analysis/interaction/traffic_interaction_table.json')
OUT_SUMMARY = Path('data/routing/route_comparison_summary.json')
OUT_DIR = Path('data/routing')

INDEX_RES = 0.01
ROAD_ATTR_RISK = {
    'footway': 0.8,
    'path': 0.85,
    'pedestrian': 0.75,
    'residential': 1.0,
    'primary': 1.3,
    'secondary': 1.2,
    'tertiary': 1.1,
    'unclassified': 1.0,
    'service': 1.0,
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def safe_name(name: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() else '_' for ch in name.strip())
    cleaned = '_'.join([p for p in cleaned.split('_') if p])
    return (cleaned[:80] or 'school').lower()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def get_target_schools() -> List[Dict[str, Any]]:
    schools = load_json(SCHOOL_PATH)
    if not isinstance(schools, list):
        raise ValueError('school_profiles_v2.json must be list')

    targets = [s for s in schools if str(s.get('pref_code', '')) == '27' and bool(s.get('high_risk'))]
    return targets[:3]


def get_lift(
    interaction_table: Dict[str, Any],
    profile: str = 'child',
    party: str = 'pedestrian',
    weather: str = 'cloudy',
    road_surface: str = 'wet',
    day_dim: str = 'day_dim',
    default: float = 5.0,
) -> float:
    table = interaction_table.get('table', {}) if isinstance(interaction_table, dict) else {}
    keys = [
        f'{profile}+{party}+{weather}+{road_surface}+{day_dim}',
        f'{profile}+{party}+{weather}+{road_surface}',
        f'{profile}+{party}+{weather}+{day_dim}',
        f'{profile}+{party}+{weather}',
        f'{profile}+{party}+{day_dim}',
        f'{profile}+{party}',
    ]
    for key in keys:
        row = table.get(key)
        if isinstance(row, dict) and 'lift' in row:
            try:
                return float(row['lift'])
            except Exception:
                pass
    return default


def build_grid_index(grid_data: List[Dict[str, Any]]) -> Dict[Tuple[int, int], List[Dict[str, Any]]]:
    idx: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for cell in grid_data:
        lat = cell.get('lat')
        lon = cell.get('lon')
        if lat is None or lon is None:
            continue
        key = (int(float(lat) / INDEX_RES), int(float(lon) / INDEX_RES))
        idx.setdefault(key, []).append(cell)
    return idx


def nearest_grid_risk(lat: float, lon: float, grid_idx: Dict[Tuple[int, int], List[Dict[str, Any]]]) -> float:
    ilat = int(lat / INDEX_RES)
    ilon = int(lon / INDEX_RES)
    best_dist = float('inf')
    best_risk = 0.1
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for cell in grid_idx.get((ilat + di, ilon + dj), []):
                c_lat = float(cell.get('lat', 0.0))
                c_lon = float(cell.get('lon', 0.0))
                d = (c_lat - lat) ** 2 + (c_lon - lon) ** 2
                if d < best_dist:
                    best_dist = d
                    best_risk = float(cell.get('risk_score') or 0.1)
    return max(0.0, best_risk)


def first_highway_type(highway: Any) -> Optional[str]:
    if isinstance(highway, list):
        return str(highway[0]) if highway else None
    if highway is None:
        return None
    return str(highway)


def assign_edge_risks(
    G: nx.MultiDiGraph,
    grid_idx: Dict[Tuple[int, int], List[Dict[str, Any]]],
    interaction_table: Dict[str, Any],
    hour: int = 16,
    weather: str = 'cloudy',
    road_surface: str = 'wet',
    profile: str = 'child',
) -> float:
    lift = get_lift(interaction_table, profile=profile, party='pedestrian', weather=weather, road_surface=road_surface, day_dim='day_dim')

    for u, v, k, data in G.edges(keys=True, data=True):
        n1 = G.nodes[u]
        n2 = G.nodes[v]
        lat = (float(n1.get('y', 0.0)) + float(n2.get('y', 0.0))) / 2
        lon = (float(n1.get('x', 0.0)) + float(n2.get('x', 0.0))) / 2
        base_risk = nearest_grid_risk(lat, lon, grid_idx)

        hwy = first_highway_type(data.get('highway'))
        attr_mult = ROAD_ATTR_RISK.get(hwy or '', 1.0)

        lit = str(data.get('lit', 'unknown')).lower()
        if hour >= 18 and lit in {'no', 'unknown', 'none'}:
            attr_mult *= 1.3

        sidewalk = str(data.get('sidewalk', '')).lower()
        if sidewalk == 'no':
            attr_mult *= 1.2

        edge_length = float(data.get('length') or 1.0)
        edge_risk = min(1.0, base_risk * lift * attr_mult)
        data['risk_weight'] = edge_risk * edge_length / 100.0

    return lift


def node_path_to_coords(G: nx.Graph, path: List[Any]) -> List[List[float]]:
    coords: List[List[float]] = []
    for n in path:
        nd = G.nodes[n]
        lat = float(nd.get('y'))
        lon = float(nd.get('x'))
        coords.append([lon, lat])
    return coords


def route_length_from_nodes(G: nx.MultiDiGraph, path: List[Any]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        edge_dict = G.get_edge_data(u, v) or {}
        if not edge_dict:
            continue
        best = min(edge_dict.values(), key=lambda d: float(d.get('length') or 1e18))
        total += float(best.get('length') or 0.0)
    return total


def route_weight_sum(G: nx.MultiDiGraph, path: List[Any], weight: str) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        edge_dict = G.get_edge_data(u, v) or {}
        if not edge_dict:
            continue
        best = min(edge_dict.values(), key=lambda d: float(d.get(weight) or 1e18))
        total += float(best.get(weight) or 0.0)
    return total


def compare_routes_osmnx(
    G: nx.MultiDiGraph,
    origin: Tuple[float, float],
    destination: Tuple[float, float],
) -> Dict[str, Any]:
    o_lat, o_lon = origin
    d_lat, d_lon = destination
    orig_node = ox.nearest_nodes(G, X=o_lon, Y=o_lat)
    dest_node = ox.nearest_nodes(G, X=d_lon, Y=d_lat)

    path_short = nx.shortest_path(G, orig_node, dest_node, weight='length')
    path_fast = nx.shortest_path(G, orig_node, dest_node, weight='travel_time')
    path_safe = nx.shortest_path(G, orig_node, dest_node, weight='risk_weight')

    short_distance = route_length_from_nodes(G, path_short)
    safe_distance = route_length_from_nodes(G, path_safe)

    risk_short = route_weight_sum(G, path_short, 'risk_weight')
    risk_safe = route_weight_sum(G, path_safe, 'risk_weight')

    detour_pct = ((safe_distance - short_distance) / short_distance * 100.0) if short_distance > 0 else 0.0
    risk_reduction_pct = ((risk_short - risk_safe) / risk_short * 100.0) if risk_short > 0 else 0.0

    recommendation = '最短経路と最低リスク経路は同じです。' if path_short == path_safe else '距離増加とリスク低減のバランスで最低リスク経路を検討してください。'

    return {
        'path_short': path_short,
        'path_fast': path_fast,
        'path_safe': path_safe,
        'distance_short_m': short_distance,
        'distance_safest_m': safe_distance,
        'risk_short': risk_short,
        'risk_safest': risk_safe,
        'detour_pct': detour_pct,
        'risk_reduction_pct': risk_reduction_pct,
        'path_differ': path_short != path_safe,
        'recommendation': recommendation,
        'geojson_short': node_path_to_coords(G, path_short),
        'geojson_safest': node_path_to_coords(G, path_safe),
    }


def get_pedestrian_network(lat: float, lon: float, radius_m: int = 2000) -> nx.MultiDiGraph:
    if ox is None:
        raise RuntimeError('osmnx is unavailable')
    G = ox.graph_from_point((lat, lon), dist=radius_m, network_type='walk', retain_all=False, simplify=True)
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    return G


def write_linestring_geojson(path: Path, coords: List[List[float]], props: Dict[str, Any]) -> None:
    feature = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': props,
                'geometry': {'type': 'LineString', 'coordinates': coords},
            }
        ],
    }
    path.write_text(json.dumps(feature, ensure_ascii=False, indent=2), encoding='utf-8')


def build_grid_graph(
    grid_data: List[Dict[str, Any]],
    center_lat: float,
    center_lon: float,
    lift: float,
    radius_km: float = 2.0,
) -> nx.Graph:
    selected: List[Dict[str, Any]] = []
    for c in grid_data:
        lat = c.get('lat')
        lon = c.get('lon')
        if lat is None or lon is None:
            continue
        if haversine_m(center_lat, center_lon, float(lat), float(lon)) <= radius_km * 1000.0:
            selected.append(c)

    G = nx.Graph()

    for i, c in enumerate(selected):
        nid = i
        lat = float(c['lat'])
        lon = float(c['lon'])
        risk = float(c.get('risk_score') or 0.1)
        G.add_node(nid, lat=lat, lon=lon, risk_score=risk)

    bucket: Dict[Tuple[int, int], List[int]] = {}
    for nid, nd in G.nodes(data=True):
        bi = int(nd['lat'] / 0.02)
        bj = int(nd['lon'] / 0.02)
        bucket.setdefault((bi, bj), []).append(nid)

    for nid, nd in G.nodes(data=True):
        bi = int(nd['lat'] / 0.02)
        bj = int(nd['lon'] / 0.02)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for other in bucket.get((bi + di, bj + dj), []):
                    if other <= nid:
                        continue
                    od = G.nodes[other]
                    dlat = abs(nd['lat'] - od['lat'])
                    dlon = abs(nd['lon'] - od['lon'])
                    if max(dlat, dlon) <= 0.02:
                        length = haversine_m(nd['lat'], nd['lon'], od['lat'], od['lon'])
                        avg_risk = (float(nd['risk_score']) + float(od['risk_score'])) / 2.0
                        risk_weight = avg_risk * lift * length / 100.0
                        G.add_edge(nid, other, length=length, risk_weight=risk_weight)

    return G


def nearest_grid_node(G: nx.Graph, lat: float, lon: float) -> int:
    best = None
    best_d = float('inf')
    for n, nd in G.nodes(data=True):
        d = (nd['lat'] - lat) ** 2 + (nd['lon'] - lon) ** 2
        if d < best_d:
            best_d = d
            best = n
    if best is None:
        raise RuntimeError('No grid node found')
    return int(best)


def route_weight_sum_graph(G: nx.Graph, path: List[int], weight: str) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        total += float(G[path[i]][path[i + 1]].get(weight) or 0.0)
    return total


def path_to_coords_graph(G: nx.Graph, path: List[int]) -> List[List[float]]:
    return [[float(G.nodes[n]['lon']), float(G.nodes[n]['lat'])] for n in path]


def fallback_compare_routes(
    G: nx.Graph,
    origin: Tuple[float, float],
    destination: Tuple[float, float],
) -> Dict[str, Any]:
    o_lat, o_lon = origin
    d_lat, d_lon = destination

    orig_node = nearest_grid_node(G, o_lat, o_lon)
    dest_node = nearest_grid_node(G, d_lat, d_lon)

    path_short = nx.shortest_path(G, orig_node, dest_node, weight='length')
    path_safe = nx.shortest_path(G, orig_node, dest_node, weight='risk_weight')

    short_distance = route_weight_sum_graph(G, path_short, 'length')
    safe_distance = route_weight_sum_graph(G, path_safe, 'length')

    risk_short = route_weight_sum_graph(G, path_short, 'risk_weight')
    risk_safe = route_weight_sum_graph(G, path_safe, 'risk_weight')

    detour_pct = ((safe_distance - short_distance) / short_distance * 100.0) if short_distance > 0 else 0.0
    risk_reduction_pct = ((risk_short - risk_safe) / risk_short * 100.0) if risk_short > 0 else 0.0

    recommendation = '最短経路と最低リスク経路は同じです。' if path_short == path_safe else '最低リスク経路は距離増加を伴う可能性があります。'

    return {
        'path_short': path_short,
        'path_safe': path_safe,
        'distance_short_m': short_distance,
        'distance_safest_m': safe_distance,
        'risk_short': risk_short,
        'risk_safest': risk_safe,
        'detour_pct': detour_pct,
        'risk_reduction_pct': risk_reduction_pct,
        'path_differ': path_short != path_safe,
        'recommendation': recommendation,
        'geojson_short': path_to_coords_graph(G, path_short),
        'geojson_safest': path_to_coords_graph(G, path_safe),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    schools = get_target_schools()
    grid_data = load_json(GRID_PATH)
    if not isinstance(grid_data, list):
        raise ValueError('grid_risk.json must be list')
    interaction = load_json(INTERACTION_PATH)

    tested: List[Dict[str, Any]] = []

    # First school determines global mode.
    mode = 'grid_fallback'
    first_school = schools[0] if schools else None
    if first_school is not None:
        try:
            lat = float(first_school['lat'])
            lon = float(first_school['lon'])
            G_try = get_pedestrian_network(lat, lon, radius_m=2000)
            grid_idx = build_grid_index(grid_data)
            assign_edge_risks(G_try, grid_idx, interaction, hour=16, weather='cloudy', road_surface='wet', profile='child')
            mode = 'osmnx'
        except Exception:
            mode = 'grid_fallback'

    if mode == 'osmnx':
        grid_idx = build_grid_index(grid_data)
        for school in schools:
            name = str(school.get('name') or 'school')
            lat = float(school['lat'])
            lon = float(school['lon'])
            origin = (lat, lon)
            destination = (lat + 0.004, lon + 0.003)

            G = get_pedestrian_network(lat, lon, radius_m=2000)
            assign_edge_risks(G, grid_idx, interaction, hour=16, weather='cloudy', road_surface='wet', profile='child')
            result = compare_routes_osmnx(G, origin, destination)

            base = safe_name(name)
            write_linestring_geojson(OUT_DIR / f'{base}_shortest.geojson', result['geojson_short'], {'school_name': name, 'route_type': 'shortest'})
            write_linestring_geojson(OUT_DIR / f'{base}_safest.geojson', result['geojson_safest'], {'school_name': name, 'route_type': 'safest'})

            tested.append(
                {
                    'school_name': name,
                    'distance_short_m': result['distance_short_m'],
                    'distance_safest_m': result['distance_safest_m'],
                    'detour_pct': result['detour_pct'],
                    'risk_short': result['risk_short'],
                    'risk_safest': result['risk_safest'],
                    'risk_reduction_pct': result['risk_reduction_pct'],
                    'path_differ': bool(result['path_differ']),
                }
            )
    else:
        lift = get_lift(interaction, profile='child', party='pedestrian', weather='cloudy', road_surface='wet', day_dim='day_dim')
        for school in schools:
            name = str(school.get('name') or 'school')
            lat = float(school['lat'])
            lon = float(school['lon'])
            origin = (lat, lon)
            destination = (lat + 0.004, lon + 0.003)

            G = build_grid_graph(grid_data, lat, lon, lift=lift, radius_km=2.0)
            if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
                raise RuntimeError(f'Grid graph too small for school: {name}')

            result = fallback_compare_routes(G, origin, destination)
            base = safe_name(name)
            write_linestring_geojson(OUT_DIR / f'{base}_shortest.geojson', result['geojson_short'], {'school_name': name, 'route_type': 'shortest'})
            write_linestring_geojson(OUT_DIR / f'{base}_safest.geojson', result['geojson_safest'], {'school_name': name, 'route_type': 'safest'})

            tested.append(
                {
                    'school_name': name,
                    'distance_short_m': result['distance_short_m'],
                    'distance_safest_m': result['distance_safest_m'],
                    'detour_pct': result['detour_pct'],
                    'risk_short': result['risk_short'],
                    'risk_safest': result['risk_safest'],
                    'risk_reduction_pct': result['risk_reduction_pct'],
                    'path_differ': bool(result['path_differ']),
                }
            )

    avg_detour = mean([t['detour_pct'] for t in tested]) if tested else 0.0
    avg_risk_reduction = mean([t['risk_reduction_pct'] for t in tested]) if tested else 0.0
    any_path_differ = any(bool(t['path_differ']) for t in tested)

    summary = {
        'mode': mode,
        'tested_schools': tested,
        'average_detour_pct': avg_detour,
        'average_risk_reduction_pct': avg_risk_reduction,
        'any_path_differ': any_path_differ,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'mode: {mode}')
    print(f'tested_schools_count: {len(tested)}')
    for t in tested:
        print(
            'school:',
            t['school_name'],
            f"distance_short_m={t['distance_short_m']:.1f}",
            f"distance_safest_m={t['distance_safest_m']:.1f}",
            f"detour_pct={t['detour_pct']:.2f}",
            f"risk_short={t['risk_short']:.4f}",
            f"risk_safest={t['risk_safest']:.4f}",
            f"risk_reduction_pct={t['risk_reduction_pct']:.2f}",
            f"path_differ={t['path_differ']}",
        )
    print(f'average_detour_pct: {avg_detour:.2f}')
    print(f'average_risk_reduction_pct: {avg_risk_reduction:.2f}')
    print(f'any_path_differ: {any_path_differ}')


if __name__ == '__main__':
    main()
