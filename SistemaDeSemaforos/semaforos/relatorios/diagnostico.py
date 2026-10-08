"""Comparações pareadas e conferência dos fluxos efetivamente simulados."""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t

from semaforos.arquivos import write_json, write_text


METRICS = {
    'global_halted_vehicle_seconds': ('Fila na rede (veículo·s)', -1),
    'wait_vehicle_seconds': ('Espera (veículo·s)', -1),
    'arrived': ('Veículos que chegaram', 1),
    'unfinished': ('Veículos ainda em viagem', -1),
    'pending_departure': ('Veículos aguardando partida', -1),
    'mean_travel_time_seconds': ('Tempo médio de viagem concluída (s)', -1),
    'pedestrian_wait_person_seconds': ('Espera de pedestres (pessoa·s)', -1),
}


def paired_metrics(runs, reference='network_reference'):
    """Benefício positivo significa melhora; IC t é exploratório, por métrica."""
    complete = runs[runs['episode_complete'].fillna(False)].copy()
    if complete.duplicated(['seed', 'controller']).any():
        raise ValueError('Há mais de um episódio por controlador e semente')
    baseline = complete[complete.controller == reference].set_index('seed')
    rows = []
    for controller, candidate in complete[complete.controller != reference].groupby('controller'):
        candidate = candidate.set_index('seed')
        for metric, (label, direction) in METRICS.items():
            if metric not in complete:
                continue
            pairs = pd.concat([baseline[metric].rename('reference'), candidate[metric].rename('candidate')], axis=1)
            pairs = pairs.apply(pd.to_numeric, errors='coerce').dropna()
            if pairs.empty:
                continue
            pairs = pairs[np.isfinite(pairs.to_numpy(dtype=float)).all(axis=1)]
            if pairs.empty:
                continue
            benefit = direction * (pairs.candidate - pairs.reference)
            n, mean = len(benefit), float(benefit.mean())
            half = float(t.ppf(0.975, n - 1) * benefit.std(ddof=1) / np.sqrt(n)) if n > 1 else None
            base = float(pairs.reference.mean())
            rows.append({'controller': controller, 'metric': metric, 'label': label, 'pairs': n,
                         'reference_mean': base, 'candidate_mean': float(pairs.candidate.mean()),
                         'benefit_mean': mean, 'improvement_percent': mean * 100 / abs(base) if base else None,
                         'benefit_ci95_low': mean - half if half is not None else None,
                         'benefit_ci95_high': mean + half if half is not None else None,
                         'improved_seeds': int((benefit > 0).sum()), 'worsened_seeds': int((benefit < 0).sum())})
    return rows


def flow_diagnostics(flows, tolerance):
    if flows.empty:
        return []
    rows = []
    complete = flows[flows['episode_complete'].fillna(False)]
    for (controller, edge), group in complete.groupby(['controller', 'edge_id']):
        measured = pd.to_numeric(group.measured_vehicles_per_hour)
        fitted = pd.to_numeric(group.fitted_vehicles_per_hour)
        realized = pd.to_numeric(group.realized_vehicles_per_hour)
        denominator = measured.clip(lower=1)
        fitted_error = (fitted - measured).abs() / denominator
        realized_error = (realized - measured).abs() / denominator
        valid = np.isfinite(realized).all() and np.isfinite(fitted).all()
        rows.append({'controller': controller, 'edge_id': edge, 'seeds': int(group['seed'].nunique()),
                     'measured_vehicles_per_hour': float(measured.mean()),
                     'fitted_vehicles_per_hour': float(fitted.mean()),
                     'realized_vehicles_per_hour': float(realized.mean()),
                     'maximum_fitted_error_percent': float(fitted_error.max() * 100),
                     'maximum_realized_error_percent': float(realized_error.max() * 100),
                     'within_tolerance': bool(valid and (fitted_error <= tolerance).all() and (realized_error <= tolerance).all())})
    return rows


def _read_table(path):
    try:
        return pd.read_csv(path, dtype={'edge_id': str})
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def export_diagnostics(output, runs, metadata):
    output = Path(output)
    config = metadata.get('evaluation_config', metadata.get('config', {}))
    demand = config.get('demand', {})
    complete = runs[runs['episode_complete'].fillna(False)]
    expected_seeds = set(runs.seed.unique())
    expected_seeds.update(metadata.get('evaluation_seeds', config.get('evaluation', {}).get('seeds', []) if metadata.get('evaluation_config') else config.get('seeds', [])))
    comparisons = paired_metrics(runs)
    tolerance = float(demand.get('calibration_tolerance', 0.2))
    calibration = flow_diagnostics(_read_table(output / 'flow_counts.csv'), tolerance)
    baseline_flows = [row for row in calibration if row['controller'] == 'network_reference']
    observed = demand.get('mode') == 'observed_counts'
    expected_edges = {row['from_edge'] for row in demand.get('edge_volumes', [])} if observed else set()
    coverage = {row['edge_id'] for row in baseline_flows} == expected_edges
    reference_seeds = set(complete.loc[complete.controller == 'network_reference', 'seed'])
    calibration_valid = bool(baseline_flows and coverage and reference_seeds == expected_seeds and
                             not metadata.get('cancelled') and
                             all(row['within_tolerance'] and row['seeds'] == len(expected_seeds) for row in baseline_flows)) if observed else None
    conclusions = []
    baseline = complete[complete.controller == 'network_reference'].set_index('seed')
    for controller, candidate in complete[complete.controller != 'network_reference'].groupby('controller'):
        candidate = candidate.set_index('seed')
        seeds = baseline.index.intersection(candidate.index)
        base, other = baseline.loc[seeds], candidate.loc[seeds]
        pair_rows = [row for row in comparisons if row['controller'] == controller]
        primary = [row for row in pair_rows if row['metric'] in ('global_halted_vehicle_seconds', 'wait_vehicle_seconds')]
        same_demand = bool(len(seeds) and 'demand_sha256' in complete and
                           base.demand_sha256.notna().all() and other.demand_sha256.notna().all() and
                           (base.demand_sha256 == other.demand_sha256).all() and
                           (base.simulated_seconds == other.simulated_seconds).all())
        for field in ('measurement_start_seconds', 'measurement_end_seconds', 'measured_seconds'):
            if field in complete:
                same_demand = same_demand and bool((base[field] == other[field]).all())
        full = bool(set(seeds) == expected_seeds and len(complete) == len(runs) and not metadata.get('cancelled'))
        guards = bool(len(seeds) and {'arrived', 'unfinished', 'pending_departure', 'collision_vehicles', 'teleports_started'} <= set(complete))
        if 'measurement_complete' in complete:
            full = full and bool(base.measurement_complete.fillna(False).all() and other.measurement_complete.fillna(False).all())
        if guards:
            guards = bool((other.arrived >= base.arrived).all() and (other.unfinished <= base.unfinished).all() and
                          (other.pending_departure <= base.pending_departure).all() and
                          (other.collision_vehicles == 0).all() and (other.teleports_started == 0).all() and
                          (base.collision_vehicles == 0).all() and (base.teleports_started == 0).all())
        if 'planned_pedestrians' in complete and (base.get('planned_pedestrians', 0) > 0).any():
            guards = guards and bool({'pedestrians_arrived', 'pedestrian_wait_person_seconds'} <= set(complete))
            if guards:
                guards = bool((other.pedestrians_arrived >= base.pedestrians_arrived).all() and
                              (other.pedestrian_wait_person_seconds <= base.pedestrian_wait_person_seconds).all())
        improved = len(primary) == 2 and all(row['benefit_mean'] > 0 for row in primary)
        consistent = improved and len(seeds) >= 3 and all(row['pairs'] == len(seeds) and row['benefit_ci95_low'] is not None and row['benefit_ci95_low'] > 0 for row in primary)
        eligible = same_demand and full and guards and (not observed or calibration_valid)
        if eligible and consistent:
            status = 'Melhoria consistente nas sementes simuladas'
        elif eligible and improved:
            status = 'Melhoria média observada; evidência ainda limitada'
        elif not same_demand or not full:
            status = 'Comparação incompleta ou demanda equivalente não comprovada'
        elif not guards:
            status = 'Há perda de atendimento ou eventos; melhoria global não demonstrada'
        elif observed and not calibration_valid:
            status = 'Fluxo realizado da referência fora da tolerância; revisar calibração'
        else:
            status = 'Melhoria simultânea de filas e espera não demonstrada'
        conclusions.append({'controller': controller, 'status': status, 'paired_seeds': len(seeds),
                            'same_demand_and_horizon': same_demand, 'complete_comparison': full,
                            'service_and_events_ok': guards, 'consistent_simulated_improvement': bool(eligible and consistent)})
    intersections = _read_table(output / 'intersections.csv')
    local = []
    if not intersections.empty:
        for name, group in intersections.groupby('intersection'):
            for row in paired_metrics(group):
                if row['metric'] == 'wait_vehicle_seconds':
                    local.append({**row, 'intersection': name})
            # A tabela local usa fila própria; reaproveita comparação pareada com esse nome.
            renamed = group.rename(columns={'queue_vehicle_seconds': 'global_halted_vehicle_seconds'})
            for row in paired_metrics(renamed):
                if row['metric'] == 'global_halted_vehicle_seconds':
                    local.append({**row, 'intersection': name, 'label': 'Fila do cruzamento (veículo·s)'})
    result = {'scope': 'Resultados da simulação; não certificam melhoria no trânsito real',
              'method': 'Diferenças pareadas por semente; IC t de 95% exploratório por métrica, sem ajuste para múltiplas comparações',
              'limitations': 'Sementes de avaliação medem variação da simulação, não de treinamentos independentes. ICs pressupõem diferenças aproximadamente normais. Tempo de viagem considera apenas chegadas.',
              'demand_mode': demand.get('mode'), 'calibration_tolerance_percent': tolerance * 100,
              'partial_episodes': len(runs) - len(complete), 'cancelled': bool(metadata.get('cancelled')),
              'calibration_valid_in_reference': calibration_valid, 'calibration': calibration,
              'comparisons': comparisons, 'conclusions': conclusions, 'intersections': local,
              'measurement_source': demand.get('measurement_source')}
    from .gargalos import export_bottlenecks
    result['bottlenecks'] = export_bottlenecks(output, config, intersections, _read_table(output / 'lanes.csv'), _read_table(output / 'movements.csv'))
    write_json(output / 'diagnostico.json', result)
    for name, rows in (('melhorias', comparisons), ('validacao_demanda', calibration), ('melhorias_cruzamentos', local)):
        if rows:
            write_text(output / f'{name}.csv', pd.DataFrame(rows).to_csv(index=False))
    return result
