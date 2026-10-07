"""Demanda de caminhadas explícita e opcional, roteada pelo SUMO."""
import math
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def crossing_routes(network, targets):
    root = ET.parse(network).getroot()
    connections = root.findall('connection')
    edges = {e.get('id'): e for e in root.findall('edge')}
    owners = {t['tls_id']: t['name'] for t in targets}
    result = []
    seen = set()
    for crossing in edges.values():
        if crossing.get('function') != 'crossing':
            continue
        before = [c for c in connections if c.get('to') == crossing.get('id') and c.get('tl') in owners]
        after = [c for c in connections if c.get('from') == crossing.get('id')]
        for start in before:
            for finish in after:
                origins = [c.get('from') for c in connections if c.get('to') == start.get('from') and not c.get('from').startswith(':')]
                # O roteamento de pedestres também percorre calçadas contra o sentido da aresta.
                destinations = [c.get('from') for c in connections if c.get('to') == finish.get('to') and not c.get('from').startswith(':')]
                for origin in origins:
                    for destination in destinations:
                        if origin == destination or (origin, destination) in seen:
                            continue
                        if not all(any('pedestrian' in l.get('allow', '').split() or not l.get('allow') and 'pedestrian' not in l.get('disallow', '').split() for l in edges[e].findall('lane')) for e in (origin, destination)):
                            continue
                        seen.add((origin, destination))
                        result.append({'intersection': owners[start.get('tl')], 'crossing_id': crossing.get('id'),
                                       'from_edge': origin, 'to_edge': destination, 'persons_per_hour': 0.0})
    return result


def create_pedestrian_demand(config, output):
    settings = config.get('pedestrians', {})
    if not settings.get('enabled', False):
        return None, 0
    duration = float(config['duration_seconds'])
    speed = float(settings.get('walking_speed_meters_per_second', 0.8))
    if not math.isfinite(speed) or speed < 0.8 or speed > 3:
        raise ValueError('Velocidade dos pedestres deve ficar entre 0,8 e 3 m/s; velocidades menores exigem recalcular pisos geométricos')
    root = ET.Element('routes')
    departures = []
    known = {e.get('id'): e for e in ET.parse(config['network']).getroot().findall('edge')}
    seen = set()
    flows = settings.get('flows', [])
    for index, flow in enumerate(flows):
        origin, destination = flow.get('from_edge'), flow.get('to_edge')
        rate = float(flow.get('persons_per_hour', 0))
        if not math.isfinite(rate) or rate < 0 or origin not in known or destination not in known or origin == destination:
            raise ValueError(f'Rota de pedestres {index}: origem, destino ou pessoas/h inválidos')
        if (origin, destination) in seen:
            raise ValueError('Rota de pedestres repetida; informe um único volume por par origem/destino')
        seen.add((origin, destination))
        count = math.floor(rate * duration / 3600 + 0.5)
        if len(departures) + count > 100000:
            raise ValueError('Demanda acima de 100000 pedestres por episódio')
        for number in range(count):
            departures.append((duration * (number + 0.5) / count, index, number, flow))
    if not departures:
        raise ValueError('Informe volumes de pedestres que gerem ao menos uma pessoa no episódio')
    for depart, index, number, flow in sorted(departures, key=lambda item: item[0]):
        person = ET.SubElement(root, 'person', id=f'ped_{index}_{number}', depart=f'{depart:.3f}')
        ET.SubElement(person, 'walk', {'from': flow['from_edge'], 'to': flow['to_edge'], 'speed': str(speed)})
    path = Path(output) / 'pedestrians.rou.xml'
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    (Path(output) / 'pedestrian_manifest.json').write_text(json.dumps({'synthetic': settings.get('synthetic', True),
        'planned_pedestrians': len(departures), 'speed_meters_per_second': speed, 'flows': flows}, ensure_ascii=False, indent=2), encoding='utf-8')
    return path, len(departures)
