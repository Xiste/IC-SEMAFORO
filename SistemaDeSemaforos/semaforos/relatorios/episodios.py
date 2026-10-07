"""Exporta registros completos ou parciais com a cobertura explícita."""
from pathlib import Path
import pandas as pd

from semaforos.arquivos import write_text
from semaforos.arquivos import read_json


DETAIL_FIELDS = {'signals', 'intersections', 'pedestrian_crossings', 'flow_counts', 'terminal_observation', 'episode'}


def scalar_metrics(info):
    return {key: value for key, value in info.items() if key not in DETAIL_FIELDS}


def append_episode(rows, signals, intersections, crossings, flows, info, controller, seed, reward):
    context = {'controller': controller, 'seed': seed, 'episode_complete': info.get('episode_complete', True)}
    if 'episode_number' in info:
        context['episode_number'] = info['episode_number']
    rows.append({**scalar_metrics(info), **context, 'reward': reward})
    for tls, values in info.get('signals', {}).items():
        signals.append({**context, 'tls_id': tls, **{key: value for key, value in values.items() if key != 'phase_seconds'},
                        **{f'phase_{index}_seconds': seconds for index, seconds in values.get('phase_seconds', {}).items()}})
    intersections.extend({**row, **context} for row in info.get('intersections', []))
    crossings.extend({**row, **context} for row in info.get('pedestrian_crossings', []))
    flows.extend({**row, **context} for row in info.get('flow_counts', []))


def export_details(output, intersections, crossings, flows):
    for name, rows in (('intersections', intersections), ('pedestrian_crossings', crossings), ('flow_counts', flows)):
        if rows:
            write_text(Path(output) / f'{name}.csv', pd.DataFrame(rows).to_csv(index=False))


def export_training_details(output, algorithm):
    rows, signals, intersections, crossings, flows = [], [], [], [], []
    for path in sorted((Path(output) / 'episodes').glob('*/episode_metrics.json')):
        info = read_json(path)
        if info:
            append_episode(rows, signals, intersections, crossings, flows, info, algorithm, info['seed'], info.get('reward'))
    export_details(output, intersections, crossings, flows)
    if signals:
        write_text(Path(output) / 'signals.csv', pd.DataFrame(signals).to_csv(index=False))
