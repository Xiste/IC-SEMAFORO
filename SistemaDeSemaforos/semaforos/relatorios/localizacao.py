"""Nomes legíveis da rede para os relatórios, preservando os IDs originais."""
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from semaforos.arquivos import read_json
from semaforos.caminhos import PROJECT_ROOT


class MetricLocations:
    def __init__(self, manifest, output):
        self.names = {t['tls_id']: t['name'] for t in manifest.get('targets', [])}
        self.edges, self.lanes, self.moves = {}, {}, {}
        self.osm_names = (read_json(PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json') or {}).get('ways', {})
        network = manifest.get('network') or manifest.get('config', {}).get('network')
        if not network:
            return
        path = Path(network)
        if not path.is_absolute():
            path = Path(output) / path
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            return
        for edge in root.findall('edge'):
            self.edges[edge.get('id')] = edge
            for lane in edge.findall('lane'):
                self.lanes[lane.get('id')] = (edge, lane)
        for connection in root.findall('connection'):
            if connection.get('tl'):
                key = f"{connection.get('tl')}:{connection.get('linkIndex')}"
                self.moves.setdefault(key, []).append(connection)

    def street(self, edge_id):
        edge = self.edges.get(edge_id)
        match = re.match(r'^-?(\d+)(?:#|$)', str(edge_id))
        cached = self.osm_names.get(match.group(1), {}).get('name') if match else ''
        return (edge.get('name') or cached or f'Trecho sem nome ({edge_id})') if edge is not None else ''

    def resolve(self, record, scope):
        record = {k: v for k, v in record.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
        tls = record.get('tls_id', '')
        crossing = record.get('intersection') or self.names.get(tls, '')
        origins, destinations, senses = [], [], []
        def lane_ids(value):
            return str(value).split('|') if value else []
        incoming = lane_ids(record.get('incoming_lanes'))
        outgoing = lane_ids(record.get('outgoing_lanes'))
        if record.get('lane_id'):
            incoming.append(record['lane_id'])
        for connection in self.moves.get(record.get('movement_id'), []):
            incoming.append(f"{connection.get('from')}_{connection.get('fromLane')}")
            outgoing.append(f"{connection.get('to')}_{connection.get('toLane')}")
        for lane_id in incoming:
            if lane_id not in self.lanes:
                continue
            edge, lane = self.lanes[lane_id]
            origins.append(self.street(edge.get('id')))
            points = [tuple(map(float, p.split(','))) for p in lane.get('shape', '').split()]
            if len(points) > 1:
                previous = next((p for p in reversed(points[:-1]) if p != points[-1]), points[-1])
                dx, dy = points[-1][0] - previous[0], points[-1][1] - previous[1]
                if dx or dy:
                    directions = ['leste', 'nordeste', 'norte', 'noroeste', 'oeste', 'sudoeste', 'sul', 'sudeste']
                    senses.append('Segue para ' + directions[int((math.degrees(math.atan2(dy, dx)) + 22.5) // 45) % 8])
        for lane_id in outgoing:
            if lane_id in self.lanes:
                destinations.append(self.street(self.lanes[lane_id][0].get('id')))
        for key, values in (('from_edge', origins), ('edge_id', origins), ('to_edge', destinations)):
            if record.get(key):
                values.append(self.street(record[key]))
        edge = self.edges.get(record.get('crossing_id'))
        if edge is not None:
            origins.extend(self.street(edge_id) for edge_id in edge.get('edges', '').split())
        turn = {'s': 'Em frente', 'l': 'À esquerda', 'r': 'À direita', 't': 'Retorno',
                'L': 'À esquerda (parcial)', 'R': 'À direita (parcial)'}.get(record.get('direction'))
        if turn:
            senses.append(turn)
        def join(values):
            return ' / '.join(dict.fromkeys(v for v in values if v))
        return {'Cruzamento': crossing, 'Rua de entrada': join(origins),
                'Rua de saída': join(destinations), 'Sentido': join(senses)}
