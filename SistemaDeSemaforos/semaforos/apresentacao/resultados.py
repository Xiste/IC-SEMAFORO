"""Resumo de resultados com as mesmas execuções completas em cada comparação."""
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from semaforos.arquivos import read_json
from semaforos.caminhos import PROJECT_ROOT


REFERENCE = 'network_reference'
TRAIN_RESULTS = 'Treinos e simulações'
COMPARISONS = 'Comparações'
MODEL_COMPARISONS = 'Modelo × modelo'
COMPARISON_COMMANDS = {'rl-eval', 'run-study'}
EXECUTION_TYPES = {
    'rl-train': 'Treino', 'rl-eval': 'Avaliação do modelo',
    'run-reference': 'Simulação inicial',
    'validate-demand': 'Conferência das contagens', 'run-study': 'Estudo com repetições',
}


def duration_label(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    return f'{minutes} min {seconds} s' if minutes and seconds else f'{minutes} min' if minutes else f'{seconds} s'


def execution_label(folder):
    folder = Path(folder)
    state = read_json(folder / 'job.json') or {}
    config = read_json(folder / 'cenario.json') or {}
    command = state.get('command')
    parts = [EXECUTION_TYPES.get(command, 'Execução')]
    if command in ('rl-train', 'rl-eval', 'run-study'):
        parts.append(config.get('algorithm', 'PPO'))
    if state.get('reference_model'):
        parts.append('Modelo × modelo')
    if isinstance(config.get('duration_seconds'), (int, float)):
        parts.append(duration_label(config['duration_seconds']) + ' simulados')
    if state.get('created_at'):
        when = datetime.fromtimestamp(state['created_at'], ZoneInfo('America/Sao_Paulo'))
        parts.append(when.strftime('%d/%m/%Y %H:%M'))
    return ' · '.join([*parts, folder.name])


def execution_section(command, reference_model=None):
    if command == 'rl-eval' and reference_model:
        return MODEL_COMPARISONS
    return COMPARISONS if command in COMPARISON_COMMANDS else TRAIN_RESULTS


def _read_table(path, **options):
    try:
        return pd.read_csv(path, **options)
    except (OSError, ValueError):
        return pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=4)
def _results_excel_snapshot(output, signature, evaluation=None):
    from semaforos.relatorios.tabela_treino import training_metrics_table, metrics_excel
    output = Path(output).resolve()
    sheets = comparison_sheets(Path(evaluation) if evaluation else output)
    summary = read_json(output / 'summary.json') or {}
    repeated = {}
    metrics = [training_metrics_table(output)]
    if summary.get('reference_model_path'):
        metrics[0]['Controle'] = metrics[0]['Controle'].replace({
            summary['reference_controller']: 'Modelo B',
            summary['algorithm']: 'Modelo A',
        })
    if evaluation:
        evaluated_metrics = training_metrics_table(Path(evaluation))
        evaluated_metrics['Origem'] = 'Avaliação vinculada/' + evaluated_metrics['Origem']
        metrics.append(evaluated_metrics)
    for item in summary.get('completed_repetitions', []):
        folder = Path(item['evaluation_output'])
        for name, table in comparison_sheets(folder).items():
            repeated.setdefault(name, []).append(table.assign(Repetição=item['repetition']))
        for execution in (folder.parent / 'train', folder):
            table = training_metrics_table(execution)
            table['Origem'] = f"Repetição {item['repetition']}/{execution.name}/" + table['Origem']
            metrics.append(table)
    sheets.update({name: pd.concat(tables, ignore_index=True) for name, tables in repeated.items()})
    return metrics_excel(pd.concat(metrics, ignore_index=True) if len(metrics) > 1 else metrics[0], sheets)


def render_training_metrics(output, key, running=False, *, download_label='Baixar resultados em Excel', evaluation=None):
    """Oferece um único Excel para a execução selecionada."""
    output = Path(output)
    if not output.exists():
        return
    paths = sorted([*output.glob('*.csv'), *output.glob('episodes/*/episode_metrics.json'),
                    *output.glob('episodes/*/live_history.csv'), *output.glob('episodes/*/actions.csv'),
                    *output.glob('optimizer/*.csv'), *output.glob('summary.json')])
    if evaluation:
        paths += sorted(Path(evaluation).glob('*.csv')) + [Path(evaluation) / 'summary.json']
        paths += sorted(Path(evaluation).glob('episodes/*/*'))
    if (output / 'study_plan.json').is_file():
        paths += sorted(path for path in output.glob('repetition_*/**/*')
                        if path.suffix == '.csv' or path.name in ('episode_metrics.json', 'summary.json', 'manifest.json'))
    if not paths:
        return
    if running:
        st.caption('O Excel completo ficará disponível quando a execução terminar ou for interrompida.')
        return
    signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths if path.is_file())
    with st.spinner('Organizando os resultados...'):
        data = _results_excel_snapshot(str(output), signature, str(evaluation) if evaluation else None)
    st.download_button(download_label, data,
        file_name=f'resultados_{output.parent.name if output.name == "execucao" else output.name}.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        key=f'{key}_excel_download', on_click='ignore')


def render_technical_files(folder, key):
    folder = Path(folder)
    files = sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix in ('.csv', '.json', '.md', '.xlsx'))
    with st.expander('Arquivos técnicos', expanded=False):
        selected = st.selectbox('Arquivo para baixar', [''] + files,
            format_func=lambda name: 'Selecione um arquivo' if not name else name,
            key=f'{key}_file_{folder}')
        if selected:
            st.download_button('Baixar arquivo selecionado', (folder / selected).read_bytes(),
                               file_name=selected, key=f'{key}_file_download')


def _completed_rows(table):
    if 'episode_complete' not in table:
        return table
    complete = table['episode_complete']
    return table[complete.eq(True) | complete.astype('string').str.strip().str.casefold().eq('true').fillna(False)]


def _paired_runs(runs, candidate, reference=REFERENCE):
    complete = _completed_rows(runs).dropna(subset=['seed'])
    baseline = complete[complete['controller'] == reference]
    evaluated = complete[complete['controller'] == candidate]
    paired = baseline.merge(evaluated, on='seed', suffixes=('_before', '_after'), validate='one_to_one')
    for field in ('demand_sha256', 'simulated_seconds', 'measurement_start_seconds',
                  'measurement_end_seconds', 'measured_seconds'):
        if field in runs:
            before, after = paired[f'{field}_before'], paired[f'{field}_after']
            paired = paired[before.eq(after) | (before.isna() & after.isna())]
    return paired


def _comparison_metrics(paired):
    metrics = [('mean_trip_waiting_seconds', 'Espera média nas viagens concluídas', 's'),
               ('mean_travel_time_seconds', 'Tempo médio das viagens concluídas', 's'),
               ('arrived', 'Veículos que concluíram a viagem', 'veículos'),
               ('unfinished', 'Veículos ainda em viagem', 'veículos'),
               ('pending_departure', 'Veículos aguardando entrar na rede', 'veículos')]
    if 'mean_global_queue_vehicles_before' in paired:
        metrics.append(('mean_global_queue_vehicles', 'Veículos parados, em média', 'veículos'))
    if 'planned_pedestrians_before' in paired and paired['planned_pedestrians_before'].gt(0).any():
        metrics.append(('pedestrians_arrived', 'Pedestres que chegaram', 'pessoas'))
    rows = []
    for metric, label, unit in metrics:
        before, after = f'{metric}_before', f'{metric}_after'
        values = paired.dropna(subset=[before, after]) if before in paired and after in paired else pd.DataFrame()
        old, new = (values[before].mean(), values[after].mean()) if not values.empty else (None, None)
        difference = new - old if old is not None else None
        rows.append({'Indicador': label, 'Tempos iniciais': old, 'Controle avaliado': new,
                     'Diferença': difference, 'Unidade': unit, 'Pares válidos': len(values),
                     'Resultado': _impact(difference, higher_is_better=metric in ('arrived', 'pedestrians_arrived'))})
    return pd.DataFrame(rows)


def comparison_table(runs, candidate):
    paired = _paired_runs(runs, candidate)
    return _comparison_metrics(paired), len(paired)


def _impact(difference, *, higher_is_better=False):
    if difference is None or not math.isfinite(difference):
        return 'Sem dados'
    if math.isclose(difference, 0, abs_tol=1e-9):
        return 'Estável'
    return 'Melhorou' if (difference > 0) == higher_is_better else 'Piorou'


EPISODE_METRICS = (
    ('planned_vehicles', 'Veículos programados', 'veículos'),
    ('departed', 'Veículos que entraram', 'veículos'),
    ('arrived', 'Viagens concluídas', 'veículos'),
    ('unfinished', 'Veículos ainda em viagem', 'veículos'),
    ('pending_departure', 'Veículos aguardando entrada', 'veículos'),
    ('mean_trip_waiting_seconds', 'Espera média por viagem concluída', 's'),
    ('mean_travel_time_seconds', 'Tempo médio por viagem concluída', 's'),
    ('mean_global_queue_vehicles', 'Veículos parados, em média', 'veículos'),
    ('planned_pedestrians', 'Pedestres programados', 'pessoas'),
    ('pedestrians_departed', 'Pedestres que iniciaram a caminhada', 'pessoas'),
    ('pedestrians_arrived', 'Pedestres que chegaram', 'pessoas'),
)


def _number(value):
    if pd.isna(value) or not math.isfinite(float(value)):
        return 'Sem dados'
    number = float(value)
    return f'{number:,.0f}'.replace(',', '.') if number.is_integer() else f'{number:,.1f}'.translate(str.maketrans(',.', '.,'))


def _episode_view(episodes, key, view):
    if episodes.empty:
        st.info('As métricas aparecem após a primeira simulação registrar dados.')
        return
    complete = _completed_rows(episodes)
    if view == 'Métricas' and len(episodes) > 1:
        index = st.selectbox('Simulação', list(range(len(episodes))),
            index=int(episodes.index.get_loc(complete.index[-1])) if not complete.empty else len(episodes) - 1,
            format_func=lambda i: f"Simulação {i + 1}" + (' · parcial' if episodes.index[i] not in complete.index else ''),
            key=f'{key}_episode')
        row = episodes.iloc[index]
    else:
        row = (complete if not complete.empty else episodes).iloc[-1]
    measured = row.get('simulated_seconds')
    number = row.get('episode_number', row.get('episode'))
    context = []
    if pd.notna(number):
        context.append(f'Simulação {int(number)}')
    if pd.notna(measured):
        context.append(f'{duration_label(measured)} simulados')
    if row.name not in complete.index:
        context.append('Parcial')
    if context:
        st.caption(' · '.join(context))
    if view == 'Métricas':
        indicators = [item for item in EPISODE_METRICS
                      if item[0] in row and (not item[0].startswith(('pedestrians_', 'planned_pedestrians'))
                                             or row.get('planned_pedestrians', 0) > 0)]
        if indicators:
            st.dataframe(pd.DataFrame([{'Indicador': label, 'Valor': row[field], 'Unidade': unit}
                                       for field, label, unit in indicators]), hide_index=True)
        return
    indicators = list(EPISODE_METRICS[:3])
    if row.get('planned_pedestrians', 0) > 0:
        indicators.append(EPISODE_METRICS[-1])
    for column, (field, label, _) in zip(st.columns(len(indicators)), indicators):
        column.metric(label, _number(row.get(field)))


def render_execution_results(output, key, view, *, download_label='Baixar resultados em Excel', evaluation=None):
    output = Path(output)
    summary = read_json(output / 'summary.json') or {}
    if (output / 'runs.csv').is_file():
        result_overview(output, key, view=view)
    elif summary.get('kind') == 'repeated_study':
        st.metric('Treinos e avaliações concluídos', f"{summary['completed_count']} de {summary['plan']['repetitions']}")
        if view == 'Métricas' and summary.get('aggregate'):
            rows = [row for row in summary['aggregate'] if row['controller'] != 'queue_actuated']
            aggregate = pd.DataFrame(rows, columns=['controller', 'label', 'mean_benefit',
                                                    'benefit_ci95_low', 'benefit_ci95_high']).rename(columns={
                'controller': 'Controle', 'label': 'Indicador', 'mean_benefit': 'Ganho médio',
                'benefit_ci95_low': 'Limite inferior (95%)', 'benefit_ci95_high': 'Limite superior (95%)',
            })
            if not aggregate.empty:
                st.dataframe(aggregate, hide_index=True)
        if view == 'Métricas' and summary.get('completed_repetitions'):
            repetitions = {item['repetition']: item for item in summary['completed_repetitions']}
            selected = st.selectbox('Repetição para detalhar', list(repetitions),
                                    format_func=lambda value: f"Repetição {value} · semente {repetitions[value]['training_seed']}",
                                    key=f'{key}_study_repetition')
            result_overview(repetitions[selected]['evaluation_output'], key, view=view)
    else:
        if view == 'Resumo' and 'timesteps' in summary:
            st.caption(f"{_number(summary['timesteps'])} decisões em "
                       f"{_number(summary.get('episodes_completed'))} simulação(ões) completa(s)"
                       f" · {duration_label(summary.get('real_seconds', 0))} de treino")
        _episode_view(_read_table(output / 'training_episodes.csv'), key, view)
        if view == 'Métricas' and 'model' in summary:
            if evaluation:
                runs = _read_table(evaluation / 'runs.csv')
                if {'controller', 'seed'} <= set(runs):
                    candidate = summary.get('algorithm', 'PPO')
                    paired = _paired_runs(runs, candidate)
                    render_signal_changes(evaluation, candidate, paired['seed'], key)
            else:
                st.caption('Avalie o modelo em Comparações para ver como ele distribui o verde em cada cruzamento.')
    if view == 'Métricas':
        render_training_metrics(output, key, download_label=download_label, evaluation=evaluation)


def intersection_wait_comparison(intersections, candidate, seeds, metric='wait_vehicle_seconds', *, reference=REFERENCE):
    """Compara indicadores locais com os mesmos pares admitidos no resumo geral."""
    required = {'intersection', 'controller', 'seed', metric}
    if not required <= set(intersections):
        return []
    local = intersections[intersections['controller'].isin((reference, candidate))].dropna(subset=['intersection'])
    complete = _completed_rows(local)
    complete = complete[complete['seed'].isin(seeds)]
    pair_keys = ['intersection', 'seed']
    measure = pair_keys + [metric]
    baseline = complete.loc[complete['controller'] == reference, measure]
    evaluated = complete.loc[complete['controller'] == candidate, measure]
    paired = baseline.merge(evaluated, on=pair_keys, suffixes=('_before', '_after'), validate='one_to_one')
    before = f'{metric}_before'
    after = f'{metric}_after'
    for column in (before, after):
        paired[column] = pd.to_numeric(paired[column], errors='coerce').astype(float)
        paired = paired[paired[column].map(math.isfinite) & paired[column].ge(0)]
    paired['difference'] = paired[after] - paired[before]
    totals = paired.groupby('intersection').agg(pairs=('seed', 'size'), before=(before, 'mean'),
        after=(after, 'mean'), difference=('difference', 'mean')).to_dict('index')
    return [{'intersection': name, **totals.get(name, {'pairs': 0, 'before': None, 'after': None, 'difference': None})}
            for name in sorted(local['intersection'].unique())]


def intersection_comparison_table(intersections, candidate, seeds, *, reference=REFERENCE, indicators=None):
    if indicators is None:
        indicators = (
            ('wait_vehicle_seconds', 'Espera acumulada', 'veículo·s'),
            ('queue_vehicle_seconds', 'Fila acumulada', 'veículo·s'),
            ('peak_halted_vehicles', 'Pico de veículos parados', 'veículos'),
        )
    rows = []
    for metric, label, unit in indicators:
        for row in intersection_wait_comparison(intersections, candidate, seeds, metric, reference=reference):
            difference = row['difference']
            before = row['before']
            rows.append({'Cruzamento': row['intersection'], 'Indicador': label, 'Unidade': unit,
                         'Referência': before, 'Controle avaliado': row['after'],
                         'Diferença': difference, 'Variação (%)': 100 * difference / before if before else None,
                         'Resultado': _impact(difference), 'Pares válidos': row['pairs']})
    return pd.DataFrame(rows).sort_values('Cruzamento', kind='stable') if rows else pd.DataFrame()


def _intersection_queue_table(intersections, candidate, paired, reference):
    if 'seed' not in intersections:
        return pd.DataFrame()
    local = intersections.copy()
    samples = paired.set_index('seed')
    if 'measured_seconds_before' in samples:
        seconds = pd.to_numeric(samples['measured_seconds_before'], errors='coerce')
    elif {'measurement_start_seconds_before', 'measurement_end_seconds_before'} <= set(samples):
        seconds = (pd.to_numeric(samples['measurement_end_seconds_before'], errors='coerce')
                   - pd.to_numeric(samples['measurement_start_seconds_before'], errors='coerce'))
    else:
        seconds = pd.to_numeric(samples.get('simulated_seconds_before', pd.Series(dtype=float)), errors='coerce')
    if 'queue_vehicle_seconds' in local:
        elapsed = local['seed'].map(seconds.where(seconds.gt(0) & seconds.map(math.isfinite)))
        local['mean_stopped_vehicles'] = pd.to_numeric(local['queue_vehicle_seconds'], errors='coerce') / elapsed
    return intersection_comparison_table(local, candidate, paired['seed'], reference=reference, indicators=(
        ('mean_stopped_vehicles', 'Veículos parados, em média', 'veículos'),
        ('peak_halted_vehicles', 'Veículos parados no pior momento', 'veículos'),
    ))


def _render_intersection_traffic(detail, baseline, model):
    st.markdown('**Quantos veículos ficaram parados neste cruzamento?**')
    measured = detail.loc[detail['Resultado'] != 'Sem dados']
    counts = measured['Resultado'].value_counts()
    if counts.empty:
        st.caption('Não há medições comparáveis para este cruzamento.')
    elif len(counts) == 1:
        outcome = counts.index[0]
        message = {
            'Melhorou': 'Todos os indicadores medidos melhoraram.',
            'Piorou': 'Todos os indicadores medidos pioraram.',
            'Estável': 'Os indicadores medidos ficaram estáveis.',
        }[outcome]
        st.write(message)
    else:
        st.write('Os indicadores medidos tiveram resultados diferentes.')

    rows = []
    for row in detail.to_dict('records'):
        unit = row['Unidade']
        change = row['Resultado']
        if change in ('Melhorou', 'Piorou'):
            difference = row['Diferença']
            sign = '+' if difference > 0 else '−'
            change += f' · {sign}{_number(abs(difference))} {unit}'
            if pd.notna(percent := row['Variação (%)']):
                change += f' ({sign}{_number(abs(percent))}%)'
        rows.append({'Indicador': row['Indicador'],
                     baseline: f"{_number(row['Referência'])} {unit}" if pd.notna(row['Referência']) else '—',
                     model: f"{_number(row['Controle avaliado'])} {unit}" if pd.notna(row['Controle avaliado']) else '—',
                     'O que mudou': change, 'Rodadas': row['Pares válidos']})

    display = pd.DataFrame(rows)
    if measured['Pares válidos'].nunique() <= 1:
        display = display.drop(columns='Rodadas')
    st.dataframe(display, hide_index=True)
    if not measured.empty and measured['Pares válidos'].nunique() == 1:
        pairs = measured['Pares válidos'].iloc[0]
        st.caption('Comparação de uma rodada com a mesma demanda.' if pairs == 1
                   else f'Média de {pairs} rodadas comparáveis, com a mesma demanda em cada rodada.')
    st.caption('Os valores contam veículos parados ao mesmo tempo. Os tempos de espera somados estão no Excel.')


@st.cache_data(show_spinner=False, max_entries=8)
def _network_locations(network, version, targets):
    from semaforos.relatorios.gargalos import intersection_locations
    return intersection_locations({'network': network,
        'targets': [{'tls_id': tls, 'name': name} for tls, name in targets]})


def _report_config(output):
    summary = read_json(output / 'summary.json') or {}
    return summary.get('evaluation_config') or summary.get('config') or read_json(output.parent / 'cenario.json') or {}


@st.cache_data(show_spinner=False, max_entries=8)
def _signal_report_geometry(network, version, targets, include_pedestrians, names_version):
    import sumolib
    from semaforos.apresentacao.sinais import controller_approaches, green_stage_choices, _movement_timings
    from semaforos.apresentacao.vias import identify_roads
    from semaforos.cenario.rede import network_programs

    names = read_json(PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json') or {}
    model = sumolib.net.readNet(network)
    details = identify_roads(model, [(t['tls_id'], t['name']) for t in targets], names.get('ways', {}))
    approaches = controller_approaches(model, details)
    programs = network_programs(network)
    stages = green_stage_choices(network, programs, targets, details, include_pedestrians)
    for tls, choices in stages.items():
        if tls not in approaches and any(label == 'Travessia de pedestres' for _, label in choices):
            approaches[tls] = 'Travessias de pedestres'
        green = dict(choices)
        stages[tls] = [(index, green.get(index) or
                        ('Verde' if any(c in phase['state'] for c in 'Gg') else
                         'Amarelo' if any(c in phase['state'] for c in 'Yy') else 'Vermelho geral'))
                       for index, phase in enumerate(programs[tls])]
    root = ET.parse(network).getroot()
    movements = {target['tls_id']: _movement_timings(root, target['tls_id'], details) for target in targets}
    return stages, approaches, programs, movements


def signal_green_comparison(signals, candidate, seeds, targets, stages, *, reference=REFERENCE, approaches=None):
    keys = ['tls_id', 'seed']
    if not {'controller', *keys} <= set(signals):
        return pd.DataFrame()
    complete = _completed_rows(signals)
    complete = complete.loc[complete['seed'].isin(seeds)]
    before = complete.loc[complete['controller'] == reference].set_index(keys)
    after = complete.loc[complete['controller'] == candidate].set_index(keys)
    if not before.index.is_unique or not after.index.is_unique:
        return pd.DataFrame()
    both = before.index.intersection(after.index)
    rows = []
    controller_numbers = {}
    for target in targets:
        tls, crossing = target['tls_id'], target['name']
        number = controller_numbers.get(crossing, 0) + 1
        controller_numbers[crossing] = number
        label = f'Conjunto {number}'
        if approach := (approaches or {}).get(tls):
            label += f' · {approach}'
        local = both[both.get_level_values('tls_id') == tls]
        for index, movement in stages.get(tls, []):
            column = f'phase_{index}_seconds'
            if column not in signals or local.empty:
                continue
            values = pd.concat([
                pd.to_numeric(before.loc[local, column], errors='coerce'),
                pd.to_numeric(after.loc[local, column], errors='coerce'),
            ], axis=1).dropna()
            if values.empty:
                continue
            initial, evaluated = values.mean().tolist()
            duration = f'phase_{index}_mean_duration_seconds'
            count = f'phase_{index}_completed_count'
            durations = pd.DataFrame({
                label: pd.to_numeric(side.loc[values.index, duration], errors='coerce')
                if duration in side else None
                for label, side in (('before', before), ('after', after))
            }, index=values.index)
            observed_pairs = durations.dropna()
            duration_difference = (observed_pairs['after'] - observed_pairs['before']).mean()
            counts = [pd.to_numeric(side.loc[values.index, count], errors='coerce').sum(min_count=1)
                      if count in side else None for side in (before, after)]
            rows.append({'Cruzamento': crossing, 'Semáforo': label, 'ID do semáforo': str(tls),
                         'Fase': index, 'Movimento ou sinal': movement,
                         'Duração média referência (s)': durations['before'].mean(),
                         'Duração média avaliada (s)': durations['after'].mean(),
                         'Diferença média pareada (s)': duration_difference,
                         'Pares com duração observada': len(observed_pairs),
                         'Passagens completas referência': counts[0], 'Passagens completas avaliadas': counts[1],
                         'Tempos iniciais (s)': initial, 'Controle avaliado (s)': evaluated,
                         'Diferença (s)': evaluated - initial})
    return pd.DataFrame(rows)


def signal_changes_table(output, candidate, seeds, *, reference=REFERENCE):
    signals = _read_table(output / 'signals.csv', dtype={'tls_id': str})
    config = _report_config(output)
    if signals.empty or len(seeds) == 0 or 'tls_id' not in signals:
        return pd.DataFrame()
    network = PROJECT_ROOT / config.get('network', '')
    names = PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json'
    saved_names = (signals.dropna(subset=['intersection']).drop_duplicates('tls_id')
                   .set_index('tls_id')['intersection'].to_dict() if 'intersection' in signals else {})
    targets = config.get('targets') or [{'tls_id': tls, 'name': saved_names.get(tls, tls)}
                                       for tls in signals['tls_id'].dropna().unique()]
    phases = sorted(int(match[1]) for column in signals if (match := re.fullmatch(r'phase_(\d+)_seconds', column)))
    stages = {target['tls_id']: [(index, f'Fase {index}') for index in phases] for target in targets}
    approaches = {}
    try:
        if network.is_file() and config.get('targets'):
            stages, approaches, _, _ = _signal_report_geometry(str(network), network.stat().st_mtime_ns, targets,
                                                       config.get('pedestrians', {}).get('enabled', False),
                                                       names.stat().st_mtime_ns if names.exists() else 0)
    except (OSError, ValueError, KeyError, IndexError, TypeError, ET.ParseError):
        pass
    return signal_green_comparison(signals, candidate, seeds, targets, stages,
                                   reference=reference, approaches=approaches).rename(columns={
        'Tempos iniciais (s)': 'Total referência (s)', 'Controle avaliado (s)': 'Total avaliado (s)',
        'Diferença (s)': 'Diferença no total (s)'})


SIGNAL_COLOR_COLUMNS = {'green': 'Verde (s)', 'yellow': 'Amarelo (s)', 'red': 'Vermelho (s)'}


def _recorded_colors(output, signals, programs, config, seeds):
    from semaforos.simulacao.cores import colors_from_trace

    if any(column.startswith('link_') for column in signals):
        return signals
    if config.get('control', config.get('ppo', {})).get('action_mode') != 'adaptive_signals':
        return signals
    runs = _read_table(output / 'runs.csv')
    if not {'controller', 'seed', 'episode_output'} <= set(runs):
        return signals
    by_run = runs.loc[runs['seed'].isin(seeds)].set_index(['controller', 'seed'])
    recovered = []
    traces = {}
    for row in signals.to_dict('records'):
        controller, seed, tls = row['controller'], row['seed'], row['tls_id']
        key = controller, seed
        if controller == REFERENCE or key not in by_run.index or tls not in programs:
            continue
        if key not in traces:
            run = by_run.loc[key]
            episode_folder = Path(str(run['episode_output'])).name
            path = output / 'episodes' / episode_folder / 'actions.csv'
            events = _read_table(path, dtype={'tls_id': str})
            traces[key] = {name: group.to_dict('records') for name, group in events.groupby('tls_id')} if {
                'tls_id', 'time_seconds', 'previous_phase', 'phase_index'} <= set(events) else {}
        phases = programs[tls]
        run = by_run.loc[key]
        try:
            stats = colors_from_trace(tls, phases, traces[key].get(tls, []),
                                     [float(row[f'phase_{i}_seconds']) for i in range(len(phases))],
                                     float(run['measurement_start_seconds']), float(run['measurement_end_seconds']),
                                     float(config['step_seconds']))
        except (KeyError, TypeError, ValueError):
            continue
        if stats:
            recovered.append({'controller': controller, 'seed': seed, 'tls_id': tls, **stats})
    return (signals.merge(pd.DataFrame(recovered), how='left', on=['controller', 'seed', 'tls_id'], validate='one_to_one')
            if recovered else signals)


def signal_color_table(output, candidate, seeds, *, reference=REFERENCE):
    from semaforos.simulacao.cores import programmed_color_times

    config = _report_config(output)
    network = PROJECT_ROOT / config.get('network', '')
    targets = config.get('targets', [])
    if not network.is_file() or not targets or len(seeds) == 0:
        return pd.DataFrame()
    names = PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json'
    try:
        _, approaches, programs, movements = _signal_report_geometry(
            str(network), network.stat().st_mtime_ns, targets, config.get('pedestrians', {}).get('enabled', False),
            names.stat().st_mtime_ns if names.exists() else 0)
    except (OSError, ValueError, KeyError, IndexError, TypeError, ET.ParseError):
        return pd.DataFrame()
    signals = _read_table(output / 'signals.csv', dtype={'tls_id': str})
    if {'controller', 'seed', 'tls_id'} <= set(signals):
        signals = _completed_rows(signals)
        signals = signals.loc[signals['seed'].isin(seeds) & signals['controller'].isin((reference, candidate))]
        signals = _recorded_colors(output, signals, programs, config, seeds)
    else:
        signals = pd.DataFrame(columns=['controller', 'tls_id'])
    rows, numbers = [], {}
    for target in targets:
        crossing, tls = target['name'], target['tls_id']
        numbers[crossing] = numbers.get(crossing, 0) + 1
        label = f'Conjunto {numbers[crossing]}'
        if tls in approaches:
            label += f' · {approaches[tls]}'
        local = signals.loc[signals['tls_id'].eq(tls)]
        recorded = local.groupby('controller').mean(numeric_only=True)
        for move in movements.get(tls, []):
            link = move['_link_index']
            for controller in (candidate, reference):
                if controller == REFERENCE and move.get('_static_cycle', False):
                    stats = programmed_color_times(programs[tls], link)
                else:
                    values = recorded.loc[controller] if controller in recorded.index else {}
                    stats = {color: values.get(f'link_{link}_{color}_mean_seconds') for color in SIGNAL_COLOR_COLUMNS}
                rows.append({'Cruzamento': crossing, 'Semáforo': label, 'ID do semáforo': tls,
                             'Via / travessia': move['Via'], 'Sentido': move['Sentido'],
                             'Movimento': move['Movimento'], 'Controle': controller,
                             **{column: stats[color] for color, column in SIGNAL_COLOR_COLUMNS.items()}})
    return pd.DataFrame(rows)


def comparison_sheets(output):
    runs = _read_table(output / 'runs.csv')
    intersections = _read_table(output / 'intersections.csv')
    groups = {}
    if not {'controller', 'seed'} <= set(runs):
        return groups
    summary = read_json(output / 'summary.json') or {}
    reference = summary.get('reference_controller', REFERENCE)
    for candidate in runs['controller'].dropna().unique():
        if candidate in (reference, 'queue_actuated'):
            continue
        try:
            paired = _paired_runs(runs, candidate, reference)
            if paired.empty:
                continue
            tables = {
                'Comparação da rede': _comparison_metrics(paired),
                'Resultado por cruzamento': intersection_comparison_table(intersections, candidate, paired['seed'], reference=reference),
                'Tempos dos semáforos': signal_color_table(output, candidate, paired['seed'], reference=reference),
                'Fases (dados técnicos)': signal_changes_table(output, candidate, paired['seed'], reference=reference),
            }
        except ValueError:
            continue
        for name, table in tables.items():
            if not table.empty:
                if reference != REFERENCE:
                    table = table.rename(columns={'Tempos iniciais': 'Valor do modelo B', 'Referência': 'Valor do modelo B',
                                                  'Controle avaliado': 'Valor do modelo A',
                                                  'Duração média referência (s)': 'Duração média modelo B (s)',
                                                  'Duração média avaliada (s)': 'Duração média modelo A (s)',
                                                  'Total referência (s)': 'Total modelo B (s)',
                                                  'Total avaliado (s)': 'Total modelo A (s)'})
                    table = table.assign(**{'Modelo A': summary.get('model_path'),
                                            'Modelo B (referência)': summary.get('reference_model_path')})
                groups.setdefault(name, []).append(table if 'Controle' in table else table.assign(Controle=candidate))
    return {name: pd.concat(tables, ignore_index=True) for name, tables in groups.items()}


def render_signal_changes(output, candidate, seeds, key, *, reference=REFERENCE, labels=None):
    table = signal_color_table(output, candidate, seeds, reference=reference)
    if table.empty:
        st.caption('Tempos por cor indisponíveis nesta avaliação.')
        return
    crossing = st.selectbox('Cruzamento para ver os tempos dos semáforos', sorted(table['Cruzamento'].unique()),
                           key=f'{key}_signal_changes_{output}_{candidate}')
    _display_color_times(table, crossing, candidate, reference, key, labels)


def _display_color_times(table, crossing, candidate, reference, key, labels=None):
    st.markdown('**Tempos por semáforo**')
    if table.empty or crossing not in table['Cruzamento'].values:
        st.caption('Tempos por cor indisponíveis neste cruzamento.')
        return
    baseline_label, candidate_label = labels or ('Programa original', candidate)
    titles = {candidate: candidate_label, reference: baseline_label}
    control = st.radio('Tempos de', [candidate, reference], horizontal=True, format_func=titles.__getitem__,
                       key=f'{key}_signal_colors_{crossing}')
    local = table.loc[table['Cruzamento'].eq(crossing) & table['Controle'].eq(control)]
    fields = list(SIGNAL_COLOR_COLUMNS.values())
    if not local[fields].notna().any().any():
        st.info('Esta avaliação não registrou tempos completos por cor para este controle. Uma nova avaliação coleta esses tempos.')
        return
    if control == REFERENCE:
        st.caption('Segundos de cada cor do programa original. Em controles com duração variável, o valor é a média observada.')
    else:
        st.caption('Duração média de cada passagem completa pela cor. Os tempos podem variar a cada ciclo.')
    if local[fields].isna().any().any():
        st.caption('Uma célula vazia indica que não há duração completa disponível para aquela cor.')
    local = local.copy()
    local['Movimento'] = [' · '.join(part for part in (road, direction, move) if part)
                          for road, direction, move in zip(local['Via / travessia'], local['Sentido'], local['Movimento'])]
    st.dataframe(local[['Semáforo', 'Movimento', *fields]], hide_index=True, column_config={
        'Semáforo': st.column_config.TextColumn(width='large'),
        'Movimento': st.column_config.TextColumn(width='large'),
        **{name: st.column_config.NumberColumn(format='%.1f', width='small') for name in fields}})


def _render_comparison_summary(table, candidate, pair_count, baseline='Tempos iniciais'):
    outcomes = table.head(3)['Resultado']
    measured = outcomes[outcomes != 'Sem dados']
    improved, worsened = measured.eq('Melhorou').sum(), measured.eq('Piorou').sum()
    if worsened and improved:
        st.info(f'{candidate} teve resultados mistos na rede. Melhorou em {improved} indicador(es) e piorou em {worsened}.')
    elif worsened:
        st.warning(f'{candidate} piorou em {worsened} de {len(measured)} indicadores principais disponíveis.')
    elif improved:
        st.success(f'{candidate} melhorou em {improved} de {len(measured)} indicadores principais disponíveis.')
    elif not measured.empty:
        st.info(f'Os indicadores principais disponíveis ficaram estáveis com {candidate}.')
    else:
        st.info('O resumo ainda não tem valores comparáveis para os indicadores principais.')
    st.caption('Resultado de 1 rodada com a mesma demanda para os dois controles.' if pair_count == 1
               else f'Média de {pair_count} rodadas, cada uma com a mesma demanda para os dois controles.')

    titles = ('Espera média', 'Tempo médio de viagem', 'Viagens concluídas na rede')
    for index, (column, title) in enumerate(zip(st.columns(3), titles)):
        row = table.iloc[index]
        before, after, difference = row['Tempos iniciais'], row['Controle avaliado'], row['Diferença']
        suffix = ' s' if row['Unidade'] == 's' else ''
        available = pd.notna(after) and pd.notna(before)
        column.metric(title, f'{_number(after)}{suffix}' if available else 'Sem dados',
            delta=f"{row['Resultado']} · {'+' if difference > 0 else ''}{_number(difference)}{suffix}" if available else None,
            delta_color='off' if row['Resultado'] == 'Estável' else 'inverse' if index < 2 else 'normal')
        if available:
            column.caption(f'{baseline}: {_number(before)}{suffix}')
    st.caption('A espera e o tempo de viagem consideram apenas as viagens concluídas.')


def _report_locations(output, names):
    fields = ['longitude', 'latitude', 'x_meters', 'y_meters']
    locations = {}
    try:
        saved = pd.read_csv(output / 'gargalos.csv')
        fields_present = [field for field in fields if field in saved]
        if 'intersection' in saved and fields_present:
            saved = saved[saved['intersection'].isin(names)].drop_duplicates('intersection')
            values = saved.set_index('intersection')[fields_present].apply(pd.to_numeric, errors='coerce')
            locations = {name: {field: value for field, value in row.items() if pd.notna(value) and math.isfinite(value)}
                         for name, row in values.to_dict('index').items()}
    except (OSError, ValueError):
        pass
    if all({'longitude', 'latitude'} <= set(locations.get(name, {})) for name in names):
        return locations
    config = _report_config(output)
    if not config.get('network') or not config.get('targets'):
        return locations
    network = Path(config['network'])
    if not network.is_absolute():
        network = PROJECT_ROOT / network
    try:
        targets = tuple((target['tls_id'], target['name']) for target in config['targets'])
        fallback = _network_locations(str(network), network.stat().st_mtime_ns, targets)
    except (OSError, ValueError, ET.ParseError):
        return locations
    return {name: {**fallback.get(name, {}), **locations.get(name, {})} for name in names}


def result_overview(output, key, *, view='Resumo'):
    output = Path(output)
    path = output / 'runs.csv'
    if not path.is_file():
        return
    try:
        runs = pd.read_csv(path)
        if not {'controller', 'seed'} <= set(runs):
            return
        summary = read_json(output / 'summary.json') or {}
        reference = summary.get('reference_controller', REFERENCE)
        against_model = reference != REFERENCE
        baseline_label = 'Modelo B' if against_model else 'Tempos iniciais'
        candidates = [c for c in runs['controller'].dropna().unique() if c not in (reference, 'queue_actuated')]
        if not candidates:
            _episode_view(runs.loc[runs['controller'] == reference], key, view)
            return
        selected = candidates[0]
        if len(candidates) > 1:
            selected = st.selectbox('Comparar os tempos iniciais com', candidates,
                format_func=lambda c: f'Modelo {c}',
                key=f'{key}_simple_controller_{output}')
        elif against_model:
            for label, algorithm, path in (
                ('Modelo A', selected, summary.get('model_path')),
                ('Modelo B (referência)', summary.get('reference_model_algorithm'), summary.get('reference_model_path')),
            ):
                if path:
                    model = Path(path)
                    folder = model.parent.parent if model.parent.name == 'execucao' else model.parent
                    st.caption(f'{label} · {algorithm} · {folder.name}')
        else:
            st.caption(f'Tempos iniciais × Modelo {selected}')
        model_label = 'Modelo A' if against_model else selected
        paired = _paired_runs(runs, selected, reference)
        if paired.empty:
            st.info('A comparação precisa de simulações completas dos dois controles com a mesma semente, demanda e duração.')
            return
        table = _comparison_metrics(paired)
        if view == 'Resumo':
            _render_comparison_summary(table, model_label, len(paired), baseline_label)
            return
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
        st.caption('Ainda não foi possível ler a comparação desta execução.')
        return

    st.subheader('Resultado por cruzamento')
    color_labels = ('Modelo B' if against_model else 'Programa original', model_label)
    try:
        local = _read_table(output / 'intersections.csv')
        detail = _intersection_queue_table(local, selected, paired, reference)
    except (OSError, ValueError):
        detail = pd.DataFrame()
    if not detail.empty:
        from semaforos.apresentacao.gargalos import select_result_intersection
        average_rows = detail['Indicador'].eq('Veículos parados, em média')
        average = not (~average_rows).any() or detail.loc[average_rows, 'Diferença'].notna().any()
        map_rows = detail.loc[average_rows if average else ~average_rows]
        rows = map_rows.rename(columns={
            'Cruzamento': 'intersection', 'Referência': 'before',
            'Controle avaliado': 'after', 'Diferença': 'difference'}).to_dict('records')
        crossing = select_result_intersection(rows, _report_locations(output, set(detail['Cruzamento'])),
            key=f'{key}_wait_{output}_{selected}', average=average)
        local = detail.loc[detail['Cruzamento'] == crossing]
        _render_intersection_traffic(local, 'Modelo B (referência)' if against_model else 'Programa original',
                                     'Modelo A' if against_model else f'Com {selected}')
        signals = signal_color_table(output, selected, paired['seed'], reference=reference)
        _display_color_times(signals, crossing, selected, reference, f'{key}_{output}', color_labels)
    else:
        st.caption('Esta execução ainda não tem contagens de veículos parados por cruzamento para exibir.')
        render_signal_changes(output, selected, paired['seed'], key, reference=reference, labels=color_labels)
    with st.expander('Ver todos os indicadores da rede'):
        st.dataframe(table.rename(columns={'Tempos iniciais': baseline_label, 'Controle avaliado': model_label}), hide_index=True)
