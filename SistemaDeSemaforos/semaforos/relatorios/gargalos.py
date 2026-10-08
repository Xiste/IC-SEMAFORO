"""Mapa por cruzamento: posições aproximadas e indicadores medidos, sem inferir acidentes."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import sumolib

from semaforos.arquivos import write_text


def intersection_locations(config):
    path = config.get('network')
    if not path or not Path(path).is_file():
        return {}
    root = ET.parse(path).getroot()
    names = {t['tls_id']: t['name'] for t in config.get('targets', [])}
    shapes = {e.get('id'): e.find('lane').get('shape', '') for e in root.findall('edge') if e.find('lane') is not None}
    points = {}
    for c in root.findall('connection'):
        if c.get('tl') not in names or c.get('from', '').startswith(':'):
            continue
        shape = shapes.get(c.get('from'), '').split()
        if shape:
            pair = shape[-1].split(',')
            points.setdefault(names[c.get('tl')], set()).add((float(pair[0]), float(pair[1])))
    network = sumolib.net.readNet(str(path))
    result = {}
    for name, coords in points.items():
        x, y = (sum(p[index] for p in coords) / len(coords) for index in (0, 1))
        latitude = longitude = None
        try:
            longitude, latitude = network.convertXY2LonLat(x, y)
        except (ImportError, RuntimeError, ValueError, TypeError):
            pass
        result[name] = {'x_meters': x, 'y_meters': y, 'longitude': longitude, 'latitude': latitude}
    return result


def bottleneck_rows(config, intersections, lanes=None, movements=None):
    if intersections.empty or 'controller' not in intersections:
        return []
    complete = intersections[intersections.episode_complete.fillna(False)]
    locations = intersection_locations(config)
    rows = []
    lanes = pd.DataFrame() if lanes is None else lanes
    movements = pd.DataFrame() if movements is None else movements
    for name, local in complete.groupby('intersection'):
        baseline = local[local.controller == 'network_reference'].set_index('seed')
        for controller, group in local.groupby('controller'):
            paired = group.set_index('seed').join(baseline[['queue_vehicle_seconds']].rename(columns={'queue_vehicle_seconds': 'reference_queue'}), how='inner')
            reference = float(paired.reference_queue.mean()) if len(paired) else None
            candidate = float(paired.queue_vehicle_seconds.mean()) if len(paired) else None
            change = (reference - candidate) * 100 / reference if reference else None
            lane_group = lanes[(lanes.controller == controller) & (lanes.intersection == name) & lanes.episode_complete.fillna(False)] if not lanes.empty and 'controller' in lanes else pd.DataFrame()
            movement_group = movements[(movements.controller == controller) & (movements.intersection == name) & movements.episode_complete.fillna(False)] if not movements.empty and 'controller' in movements else pd.DataFrame()
            jam = float(lane_group.maximum_jam_length_meters.max()) if 'maximum_jam_length_meters' in lane_group else None
            spill = float(lane_group.spillback_seconds.max()) if 'spillback_seconds' in lane_group else None
            blocked = float(movement_group.green_with_blocked_downstream_seconds.max()) if 'green_with_blocked_downstream_seconds' in movement_group else None
            status = 'Bloqueio a jusante observado' if blocked and blocked > 0 else 'Possível transbordamento de fila' if spill and spill > 0 else 'Melhorou' if change is not None and change > 0 else 'Piorou' if change is not None and change < 0 else 'Referência / sem diferença'
            colors = {'Bloqueio a jusante observado': [255, 140, 0, 200], 'Possível transbordamento de fila': [220, 160, 0, 200],
                      'Melhorou': [40, 160, 80, 200], 'Piorou': [220, 60, 60, 200], 'Referência / sem diferença': [100, 110, 130, 200]}
            rows.append({'intersection': name, 'controller': controller, 'status': status,
                         'mean_queue_vehicle_seconds': float(group.queue_vehicle_seconds.mean()),
                         'mean_wait_vehicle_seconds': float(group.wait_vehicle_seconds.mean()),
                         'peak_halted_vehicles': float(group.peak_halted_vehicles.max()),
                         'queue_improvement_percent': change, 'paired_seeds': len(paired),
                         'maximum_jam_length_meters': jam, 'worst_lane_spillback_seconds': spill,
                         'maximum_movement_blocked_green_seconds': blocked,
                         **locations.get(name, {}), 'color': colors[status]})
    return rows


def export_bottlenecks(output, config, intersections, lanes, movements):
    rows = bottleneck_rows(config, intersections, lanes, movements)
    if rows:
        write_text(Path(output) / 'gargalos.csv', pd.DataFrame(rows).drop(columns='color').to_csv(index=False))
    return rows
