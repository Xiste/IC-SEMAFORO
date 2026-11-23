"""Resumo de resultados com as mesmas execuções completas em cada comparação."""
import math
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
    if isinstance(config.get('duration_seconds'), (int, float)):
        parts.append(duration_label(config['duration_seconds']) + ' simulados')
    if state.get('created_at'):
        when = datetime.fromtimestamp(state['created_at'], ZoneInfo('America/Sao_Paulo'))
        parts.append(when.strftime('%d/%m/%Y %H:%M'))
    return ' · '.join([*parts, folder.name])


def execution_section(command):
    return COMPARISONS if command in COMPARISON_COMMANDS else TRAIN_RESULTS


def _read_table(path):
    try:
        return pd.read_csv(path)
    except (OSError, ValueError):
        return pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=4)
def _results_excel_snapshot(output, signature):
    from semaforos.relatorios.tabela_treino import training_metrics_table, metrics_excel
    return metrics_excel(training_metrics_table(Path(output)))


def render_training_metrics(output, key, running=False, *, download_label='Baixar resultados em Excel'):
    """Oferece um único Excel para a execução selecionada."""
    output = Path(output)
    if not output.exists():
        return
    paths = sorted([*output.glob('*.csv'), *output.glob('episodes/*/episode_metrics.json'),
                    *output.glob('episodes/*/live_history.csv'), *output.glob('episodes/*/actions.csv'),
                    *output.glob('optimizer/*.csv')])
    if not paths:
        return
    if running:
        st.caption('O Excel completo ficará disponível quando a execução terminar ou for interrompida.')
        return
    signature = tuple((str(path.relative_to(output)), path.stat().st_mtime_ns, path.stat().st_size) for path in paths if path.is_file())
    with st.spinner('Organizando os resultados...'):
        data = _results_excel_snapshot(str(output), signature)
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


def _paired_runs(runs, candidate):
    complete = _completed_rows(runs).dropna(subset=['seed'])
    reference = complete[complete['controller'] == REFERENCE]
    evaluated = complete[complete['controller'] == candidate]
    paired = reference.merge(evaluated, on='seed', suffixes=('_before', '_after'), validate='one_to_one')
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
        rows.append({'Indicador': label, 'Tempos iniciais': old, 'Controle avaliado': new,
                     'Diferença': new - old if old is not None else None, 'Unidade': unit})
    return pd.DataFrame(rows)


def comparison_table(runs, candidate):
    paired = _paired_runs(runs, candidate)
    return _comparison_metrics(paired), len(paired)


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
        render_training_metrics(output, key, download_label=download_label)


def intersection_wait_comparison(intersections, candidate, seeds):
    """Calcula a espera local com os mesmos pares admitidos no resumo geral."""
    required = {'intersection', 'controller', 'seed', 'wait_vehicle_seconds'}
    if not required <= set(intersections):
        return []
    local = intersections[intersections['controller'].isin((REFERENCE, candidate))].dropna(subset=['intersection'])
    complete = _completed_rows(local)
    complete = complete[complete['seed'].isin(seeds)]
    pair_keys = ['intersection', 'seed']
    measure = pair_keys + ['wait_vehicle_seconds']
    reference = complete.loc[complete['controller'] == REFERENCE, measure]
    evaluated = complete.loc[complete['controller'] == candidate, measure]
    paired = reference.merge(evaluated, on=pair_keys, suffixes=('_before', '_after'), validate='one_to_one')
    before = 'wait_vehicle_seconds_before'
    after = 'wait_vehicle_seconds_after'
    for column in (before, after):
        paired[column] = pd.to_numeric(paired[column], errors='coerce').astype(float)
        paired = paired[paired[column].map(math.isfinite) & paired[column].ge(0)]
    paired['difference'] = paired[after] - paired[before]
    totals = paired.groupby('intersection').agg(pairs=('seed', 'size'), before=(before, 'mean'),
        after=(after, 'mean'), difference=('difference', 'mean')).to_dict('index')
    return [{'intersection': name, **totals.get(name, {'pairs': 0, 'before': None, 'after': None, 'difference': None})}
            for name in sorted(local['intersection'].unique())]


@st.cache_data(show_spinner=False, max_entries=8)
def _network_locations(network, version, targets):
    from semaforos.relatorios.gargalos import intersection_locations
    return intersection_locations({'network': network,
        'targets': [{'tls_id': tls, 'name': name} for tls, name in targets]})


def _report_config(output):
    summary = read_json(output / 'summary.json') or {}
    return summary.get('evaluation_config') or summary.get('config') or read_json(output.parent / 'cenario.json') or {}


@st.cache_data(show_spinner=False, max_entries=8)
def _green_stages(network, version, targets, include_pedestrians, names_version):
    import sumolib
    from semaforos.apresentacao.sinais import green_stage_choices
    from semaforos.apresentacao.vias import identify_roads
    from semaforos.cenario.rede import network_programs

    names = read_json(PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json') or {}
    details = identify_roads(sumolib.net.readNet(network), [(t['tls_id'], t['name']) for t in targets], names.get('ways', {}))
    return green_stage_choices(network, network_programs(network), targets, details, include_pedestrians)


def signal_green_comparison(signals, candidate, seeds, targets, stages):
    keys = ['tls_id', 'seed']
    if not {'controller', *keys} <= set(signals):
        return pd.DataFrame()
    complete = _completed_rows(signals)
    complete = complete.loc[complete['seed'].isin(seeds)]
    before = complete.loc[complete['controller'] == REFERENCE].set_index(keys)
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
            rows.append({'Cruzamento': crossing, 'Semáforo': f'Conjunto {number}',
                         'Quem recebe verde': movement, 'Tempos iniciais (s)': initial,
                         'Controle avaliado (s)': evaluated, 'Diferença (s)': evaluated - initial})
    return pd.DataFrame(rows)


def render_signal_changes(output, candidate, seeds, key):
    signals = _read_table(output / 'signals.csv')
    config = _report_config(output)
    if signals.empty or len(seeds) == 0 or not config.get('network') or not config.get('targets'):
        return
    network = PROJECT_ROOT / config['network']
    names = PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json'
    targets = config['targets']
    try:
        stages = _green_stages(str(network), network.stat().st_mtime_ns, targets,
                               config.get('pedestrians', {}).get('enabled', False),
                               names.stat().st_mtime_ns if names.exists() else 0)
        table = signal_green_comparison(signals, candidate, seeds, targets, stages)
    except (OSError, ValueError, KeyError, IndexError, ET.ParseError):
        return
    if table.empty:
        return
    st.subheader('O que mudou nos semáforos')
    st.caption('Segundos totais de verde por movimento em cada rodada da avaliação. Com várias sementes, a tabela mostra a média dos pares completos.')
    crossing = st.selectbox('Cruzamento para ver os tempos de verde', sorted(table['Cruzamento'].unique()),
                           key=f'{key}_signal_changes_{output}_{candidate}')
    local = table.loc[table['Cruzamento'] == crossing].drop(columns='Cruzamento')
    if local['Semáforo'].nunique() == 1:
        local = local.drop(columns='Semáforo')
    control_column = f'{candidate} (s)'
    local = local.rename(columns={'Controle avaliado (s)': control_column})
    st.dataframe(local, hide_index=True, column_config={
        'Quem recebe verde': st.column_config.TextColumn(width='large'),
        'Tempos iniciais (s)': st.column_config.NumberColumn(format='%.1f'),
        control_column: st.column_config.NumberColumn(format='%.1f'),
        'Diferença (s)': st.column_config.NumberColumn(format='%+.1f'),
    })


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
        candidates = [c for c in runs['controller'].dropna().unique() if c not in (REFERENCE, 'queue_actuated')]
        if not candidates:
            _episode_view(runs.loc[runs['controller'] == REFERENCE], key, view)
            return
        selected = candidates[0]
        if len(candidates) > 1:
            selected = st.selectbox('Comparar os tempos iniciais com', candidates,
                format_func=lambda c: f'Modelo {c}',
                key=f'{key}_simple_controller_{output}')
        else:
            st.caption(f'Tempos iniciais × Modelo {selected}')
        paired = _paired_runs(runs, selected)
        if paired.empty:
            st.info('A comparação precisa de simulações completas dos dois controles com a mesma semente, demanda e duração.')
            return
        table = _comparison_metrics(paired)
        st.caption(f'{len(paired)} par(es) de simulações completas com a mesma demanda.')
        if view == 'Resumo':
            cards = st.columns(3)
            for column, index, title, lower_is_better in (
                    (cards[0], 0, 'Espera média', True),
                    (cards[1], 1, 'Tempo médio de viagem', True),
                    (cards[2], 2, 'Viagens concluídas na rede', False)):
                row = table.iloc[index]
                before, after, difference = row['Tempos iniciais'], row['Controle avaliado'], row['Diferença']
                suffix = ' s' if row['Unidade'] == 's' else ''
                available = pd.notna(after) and pd.notna(before)
                column.metric(title, f'{_number(after)}{suffix}' if available else 'Sem dados',
                    delta=f"{'+' if difference > 0 else ''}{_number(difference)}{suffix}" if available else None,
                    delta_color='inverse' if lower_is_better else 'normal')
                if available:
                    column.caption(f'Com os tempos iniciais: {_number(before)}{suffix}')
            st.caption('A espera e o tempo de viagem consideram as viagens concluídas. Os valores são médias das simulações comparadas.')
            return
        st.dataframe(table, hide_index=True, column_config={
            field: st.column_config.NumberColumn(format='localized')
            for field in ('Tempos iniciais', 'Controle avaliado', 'Diferença')
        })
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
        st.caption('Ainda não foi possível ler a comparação desta execução.')
        return

    render_signal_changes(output, selected, paired['seed'], key)
    try:
        local = pd.read_csv(output / 'intersections.csv')
        rows = intersection_wait_comparison(local, selected, paired['seed'])
    except (OSError, ValueError):
        rows = []
    if rows:
        from semaforos.apresentacao.gargalos import render_wait_comparison
        render_wait_comparison(rows, _report_locations(output, {row['intersection'] for row in rows}),
            key=f'{key}_wait_{output}_{selected}')
    else:
        st.caption('Esta execução ainda não tem dados de espera por cruzamento para exibir.')
