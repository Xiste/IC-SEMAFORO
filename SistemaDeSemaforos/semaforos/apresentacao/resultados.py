"""Resumo de resultados com as mesmas execuções completas em cada comparação."""
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import streamlit as st

from semaforos.arquivos import read_json
from semaforos.caminhos import PROJECT_ROOT


REFERENCE = 'network_reference'


@st.cache_data(show_spinner=False, max_entries=4)
def _results_excel_snapshot(output, signature):
    from semaforos.relatorios.tabela_treino import training_metrics_table, metrics_excel
    return metrics_excel(training_metrics_table(Path(output)))


def render_training_metrics(output, key, running=False):
    """Resumo e um Excel completo, sem tabelas ou arquivos repetidos na tela."""
    output = Path(output)
    if not output.exists():
        return
    summary = read_json(output / 'summary.json') or {}
    if 'timesteps' in summary:
        st.subheader('Resumo do treinamento')
        a, b, c = st.columns(3)
        a.metric('Simulações concluídas', summary.get('episodes_completed', 0))
        b.metric('Decisões de treino', summary['timesteps'])
        c.metric('Tempo de treinamento', f"{summary.get('real_seconds', 0):g} s")
        if summary.get('partial_episode_saved'):
            st.caption('O Excel também inclui uma simulação parcial, identificada como parcial.')
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
    st.download_button('Baixar resultados em Excel', data,
        file_name=f'resultados_{output.name}.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=f'{key}_excel_download')
    st.caption('Uma planilha com todas as métricas registradas. Dados indisponíveis ficam vazios e simulações parciais são identificadas.')


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
    summary = read_json(output / 'summary.json') or {}
    config = summary.get('evaluation_config') or summary.get('config') or read_json(output.parent / 'cenario.json') or {}
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


def result_overview(output, key):
    output = Path(output)
    path = output / 'runs.csv'
    if not path.is_file():
        return
    try:
        runs = pd.read_csv(path)
        if not {'controller', 'seed'} <= set(runs):
            return
        candidates = [c for c in runs['controller'].dropna().unique() if c != REFERENCE]
        if not candidates:
            st.info('Simulação com os tempos iniciais concluída. Treine um modelo ou compare o controle por filas para medir as diferenças.')
            return
        names = {'queue_actuated': 'Controle por filas (sem aprendizado)'}
        st.subheader('O que mudou no trânsito?')
        first_model = next((i for i, c in enumerate(candidates) if c != 'queue_actuated'), 0)
        selected = st.selectbox('Controle para comparar', candidates,
            index=first_model, format_func=lambda c: names.get(c, f'Modelo {c}'),
            key=f'{key}_simple_controller_{output}')
        paired = _paired_runs(runs, selected)
        if paired.empty:
            st.info('A comparação precisa de simulações completas dos dois controles com a mesma semente, demanda e duração.')
            return
        table = _comparison_metrics(paired)
        cards = st.columns(3)
        for column, index, title, lower_is_better in (
                (cards[0], 0, 'Espera média', True),
                (cards[1], 1, 'Tempo médio de viagem', True),
                (cards[2], 2, 'Viagens concluídas na rede', False)):
            row = table.iloc[index]
            value, difference = row['Controle avaliado'], row['Diferença']
            available = pd.notna(value) and pd.notna(difference)
            suffix = ' s' if row['Unidade'] == 's' else ''
            column.metric(title, f'{value:.1f}{suffix}' if available else 'Sem dados',
                delta=f'{difference:+.1f}{suffix}' if available else None,
                delta_color='inverse' if lower_is_better else 'normal',
                help='O número principal é a média do controle avaliado. A diferença abaixo compara com os tempos iniciais da simulação.')
        st.caption(f'Comparação de {len(paired)} par(es) de simulações completas. As viagens concluídas são contadas na rede inteira. Diferenças observadas não comprovam melhora estatística.')
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        st.caption(f'O resumo ainda não está disponível: {error}')
        return

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
