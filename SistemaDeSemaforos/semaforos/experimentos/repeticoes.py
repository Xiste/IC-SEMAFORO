"""Treinos independentes e avaliações reservadas, executados somente sob comando."""
import copy
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t

from semaforos.arquivos import write_json, write_text
from semaforos.experimentos.tarefas import cancellation_requested


def study_plan(config):
    from semaforos.algoritmos.registro import get_algorithm
    algorithm = get_algorithm(config.get('algorithm', 'PPO'))
    train = config.get('study', {}).get('training_seeds', config['seeds'])
    evaluate = config.get('evaluation', {}).get('seeds', [])
    for seeds in (train, evaluate):
        if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or not 0 <= s < 2**31 for s in seeds):
            raise ValueError('Use listas de sementes inteiras distintas entre 0 e 2147483647')
    if set(train) & set(evaluate):
        raise ValueError('Sementes dos treinos e avaliações precisam ser separadas')
    if len(train) > 50:
        raise ValueError('Limite de 50 treinamentos por estudo')
    return {'training_seeds': list(train), 'evaluation_seeds': list(evaluate), 'repetitions': len(train),
            'evaluation_episodes': len(train) * len(evaluate) * 3,
            'requested_training_timesteps': len(train) * int(config.get(algorithm.config_key, {}).get('total_timesteps', 2048))}


def aggregate_repetitions(rows):
    if not rows:
        return []
    table = pd.DataFrame(rows)
    aggregates = []
    for (controller, metric), group in table.groupby(['controller', 'metric']):
        values = pd.to_numeric(group.benefit_mean, errors='coerce').dropna()
        n = len(values)
        if not n:
            continue
        mean = float(values.mean())
        deviation = float(values.std(ddof=1)) if n > 1 else None
        half = float(t.ppf(.975, n - 1) * deviation / np.sqrt(n)) if n > 1 else None
        aggregates.append({'controller': controller, 'metric': metric, 'label': group.label.iloc[0],
            'independent_training_repetitions': n, 'mean_benefit': mean, 'std_between_training_repetitions': deviation,
            'benefit_ci95_low': mean - half if half is not None else None,
            'benefit_ci95_high': mean + half if half is not None else None,
            'positive_repetitions': int((values > 0).sum()), 'negative_repetitions': int((values < 0).sum())})
    return aggregates


def run_study(config, output):
    from semaforos.experimentos.rl import train_rl, evaluate_rl
    plan = study_plan(config)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'study_plan.json', plan)
    completed, comparisons = [], []
    cancelled = False
    for index, seed in enumerate(plan['training_seeds'], 1):
        if cancellation_requested(output):
            cancelled = True
            break
        current = copy.deepcopy(config)
        current['seeds'] = [seed]
        folder = output / f'repetition_{index:03d}_seed_{seed}'
        folder.mkdir()
        write_json(output / 'progress.json', {'stage': 'training', 'repetition': index, 'total_repetitions': plan['repetitions'],
                                            'training_seed': seed, 'active_output': str(folder / 'train')})
        try:
            train = train_rl(current, folder / 'train')
        except InterruptedError:
            if not cancellation_requested(output):
                raise
            cancelled = True
            break
        if train.get('cancelled') or cancellation_requested(output):
            cancelled = True
            break
        write_json(output / 'progress.json', {'stage': 'evaluation', 'repetition': index, 'total_repetitions': plan['repetitions'],
                                            'training_seed': seed, 'active_output': str(folder / 'evaluation')})
        try:
            evaluated = evaluate_rl(current, folder / 'evaluation', train['model'], seeds=plan['evaluation_seeds'])
        except InterruptedError:
            if not cancellation_requested(output):
                raise
            cancelled = True
            break
        if evaluated.get('cancelled') or not evaluated.get('comparison_complete'):
            cancelled = True
            break
        completed.append({'repetition': index, 'training_seed': seed, 'model': train['model'],
                          'evaluation_output': str(folder / 'evaluation'), 'conclusions': evaluated['diagnostico']['conclusions']})
        comparisons.extend({**row, 'repetition': index, 'training_seed': seed} for row in evaluated['diagnostico']['comparisons'])
        write_json(output / 'study_completed.json', completed)
    aggregate = aggregate_repetitions(comparisons)
    summary = {'kind': 'repeated_study', 'plan': plan, 'completed_repetitions': completed,
               'completed_count': len(completed), 'cancelled': cancelled,
               'comparison_complete': not cancelled and len(completed) == plan['repetitions'],
               'aggregate': aggregate,
               'scope': 'IC exploratório entre médias de treinamentos independentes; sementes de avaliação não são contadas como novos treinos.'}
    for name, rows in (('study_comparisons', comparisons), ('study_aggregate', aggregate)):
        if rows:
            write_text(output / f'{name}.csv', pd.DataFrame(rows).to_csv(index=False))
    write_json(output / 'summary.json', summary)
    write_json(output / 'progress.json', {'stage': 'cancelled' if cancelled else 'completed',
                                        'completed_repetitions': len(completed), 'total_repetitions': plan['repetitions']})
    return summary
