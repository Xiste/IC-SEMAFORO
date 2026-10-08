"""Volumes por cruzamento com distribuição explícita pelas aproximações."""
import math
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def _inventory(path, targets, version):
    root = ET.parse(path).getroot()
    edges = {e.get('id'): e for e in root.findall('edge')}
    names = dict(targets)
    result = {name: set() for name in names.values()}
    for c in root.findall('connection'):
        if c.get('tl') not in names:
            continue
        edge = edges[c.get('from')]
        if edge.get('function') in ('crossing', 'walkingarea', 'internal'):
            continue
        lanes = edge.findall('lane')
        if any('passenger' not in l.get('disallow', '').split() and
               (not l.get('allow') or 'passenger' in l.get('allow').split() or 'all' in l.get('allow').split()) for l in lanes):
            result[names[c.get('tl')]].add(edge.get('id'))
    return {name: sorted(ids) for name, ids in result.items()}


def intersection_entries(config):
    path = Path(config['network']).resolve()
    return _inventory(str(path), tuple((t['tls_id'], t['name']) for t in config['targets']), path.stat().st_mtime_ns)


def distribute_volumes(totals, shares, inventory, include_zero=False):
    if len({row['intersection'] for row in totals}) != len(totals):
        raise ValueError('Informe um único total por cruzamento')
    grouped = {}
    seen = set()
    for row in shares:
        name, edge = row['intersection'], row['edge_id']
        share = float(row['percent'])
        if name not in inventory or edge not in inventory[name] or not math.isfinite(share) or not 0 <= share <= 100:
            raise ValueError('Distribuição contém entrada desconhecida ou percentual inválido')
        if (name, edge) in seen:
            raise ValueError('Há uma entrada repetida na distribuição')
        seen.add((name, edge))
        grouped.setdefault(name, []).append((edge, share))
    result, used = [], set()
    for row in totals:
        name, rate = row['intersection'], float(row['vehicles_per_hour'])
        if name not in inventory or not math.isfinite(rate) or rate < 0:
            raise ValueError('Total por cruzamento deve ser finito e não negativo')
        if rate == 0 and not include_zero:
            continue
        entries = grouped.get(name, [])
        if not entries or abs(sum(percent for _, percent in entries) - 100) > 1e-6:
            raise ValueError(f'Percentuais de {name} devem somar 100%')
        if {edge for edge, _ in entries} != set(inventory[name]):
            raise ValueError(f'Informe o percentual de todas as entradas de {name}, inclusive zero')
        for edge, percent in entries:
            if edge in used:
                raise ValueError('Uma entrada pertence a mais de um cruzamento; revise a associação antes de distribuir')
            used.add(edge)
            result.append({'from_edge': edge, 'vehicles_per_hour': rate * percent / 100,
                           'to_edge': '', 'zero_measured': include_zero or percent == 0})
    if not any(row['vehicles_per_hour'] > 0 for row in result):
        raise ValueError('Informe ao menos um total positivo')
    return result
