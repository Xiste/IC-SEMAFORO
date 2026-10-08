"""Exporta registros completos ou parciais com a cobertura explícita."""
from pathlib import Path
import pandas as pd

from semaforos.arquivos import write_text
from semaforos.arquivos import read_json


DETAIL_FIELDS = {'signals', 'intersections', 'pedestrian_crossings', 'flow_counts', 'lanes', 'movements', 'vehicle_classes', 'terminal_observation', 'episode'}


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
    # Os arquivos por episódio também cobrem avaliações e referência, sem duplicar argumentos.
    export_extended_details(output)


def export_extended_details(output):
    output = Path(output)
    contexts = {}
    for name in ('intersections', 'flow_counts'):
        path = output / f'{name}.csv'
        if path.is_file():
            table = pd.read_csv(path)
            for row in table.to_dict('records'):
                if 'episode_number' in row:
                    contexts[int(row['episode_number'])] = {key: row[key] for key in ('controller', 'seed', 'episode_complete', 'episode_number') if key in row}
    rows = {'lanes': [], 'movements': [], 'vehicle_classes': []}
    for path in sorted((output / 'episodes').glob('*/episode_metrics.json')):
        info = read_json(path)
        if info:
            context = contexts.get(info['episode_number'], {'seed': info['seed'], 'episode_complete': info['episode_complete'], 'episode_number': info['episode_number']})
            for name in rows:
                rows[name].extend({**row, **context} for row in info.get(name, []))
    for name, values in rows.items():
        if values:
            write_text(output / f'{name}.csv', pd.DataFrame(values).to_csv(index=False))


def export_training_details(output, algorithm):
    rows, signals, intersections, crossings, flows = [], [], [], [], []
    for path in sorted((Path(output) / 'episodes').glob('*/episode_metrics.json')):
        info = read_json(path)
        if info:
            append_episode(rows, signals, intersections, crossings, flows, info, algorithm, info['seed'], info.get('reward'))
    export_details(output, intersections, crossings, flows)
    if signals:
        write_text(Path(output) / 'signals.csv', pd.DataFrame(signals).to_csv(index=False))
