"""Referências do cenário para os limites editáveis do treinamento."""
from semaforos.apresentacao.sinais import signal_presentation
import pandas as pd
import streamlit as st
from hashlib import sha256


@st.cache_data(show_spinner=False)
def _adaptive_limit_rows(network, version, targets, specs, labels):
    import xml.etree.ElementTree as ET
    root = ET.parse(network).getroot()
    names = dict(targets)
    from semaforos.cenario.rede import network_programs
    programs = network_programs(network)
    rows = []
    turns = {'s': 'seguir em frente', 'l': 'virar à esquerda', 'L': 'virar à esquerda',
             'r': 'virar à direita', 'R': 'virar à direita', 't': 'retornar'}
    for spec in specs:
        if spec['kind'] != 'green':
            continue
        tls, index = spec['tls_id'], spec['phase_index']
        opened = {i for i, color in enumerate(programs[tls][index]['state']) if color in 'Gg'}
        entries = sorted({labels.get(c.get('from'), 'Travessia de pedestres' if c.get('from', '').startswith(':') else c.get('from')) + ': ' + turns.get(c.get('dir'), 'travessia')
                          for c in root.findall('connection') if c.get('tl') == tls and int(c.get('linkIndex')) in opened})
        rows.append({'key': f'{tls}:{index}', 'crossing': names[tls], 'entries': '; '.join(entries),
                     'minimum_seconds': spec['durations_seconds'][0], 'maximum_seconds': spec['durations_seconds'][2]})
    return rows


def adaptive_limits_editor(config, specs, labels, key, *, selected_crossing=None, selected_controller=None, map_only=False):
    """Limites por entradas atendidas, sem navegação por etapas do programa."""
    import xml.etree.ElementTree as ET
    from semaforos.apresentacao.estado import configuration_key
    key = configuration_key(key)
    from pathlib import Path
    rows = _adaptive_limit_rows(str(config['network']), Path(config['network']).stat().st_mtime_ns,
        tuple((t['tls_id'], t['name']) for t in config['targets']), specs, labels)
    signature = sha256(repr(rows).encode()).hexdigest()[:16]
    namespace = f'{key}_{signature}'
    saved = st.session_state.setdefault(namespace + '_values', {})
    crossings = list(dict.fromkeys(r['crossing'] for r in rows))
    crossing = selected_crossing if map_only or selected_crossing in crossings else st.selectbox('Cruzamento para ajustar', crossings, key=namespace + '_crossing')
    local = [{**r, **saved.get(r['key'], {})} for r in rows if r['crossing'] == crossing
             and (not selected_controller or r['key'].rsplit(':', 1)[0] == selected_controller)]
    if local and map_only:
        st.caption('Ajuste os limites de verde das entradas atendidas juntas.')
        for row in local:
            with st.container(border=True):
                st.markdown('**Entradas atendidas**')
                for entry in row['entries'].split('; '):
                    st.write('Travessia de pedestres' if entry.startswith('Travessia de pedestres:') else entry)
                minimum, maximum = st.columns(2)
                settings = {}
                for column, field, label in ((minimum, 'minimum_seconds', 'Verde mínimo (s)'),
                                             (maximum, 'maximum_seconds', 'Verde máximo (s)')):
                    widget_key = f'{namespace}_{row["key"]}_{field}'
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = float(row[field]) if row[field] is not None else None
                    with column:
                        settings[field] = st.number_input(label, min_value=.1, step=1., key=widget_key)
                saved[row['key']] = settings
    elif local:
        st.caption('O modelo escolhe quais entradas atender e por quanto tempo manter o verde, dentro destes limites. Entradas compatíveis podem ser atendidas juntas.')
        edited = st.data_editor(pd.DataFrame(local), hide_index=True, width='stretch',
            key=f'{namespace}_{crossing}_{selected_controller or "all"}_editor', disabled=['key', 'crossing', 'entries'],
            column_config={'key': None, 'crossing': None,
                'entries': st.column_config.TextColumn('Entradas atendidas'),
                'minimum_seconds': st.column_config.NumberColumn('Verde mínimo (s)', min_value=.1),
                'maximum_seconds': st.column_config.NumberColumn('Verde máximo (s)', min_value=.1)})
        for row in edited.to_dict('records'):
            saved[row['key']] = {k: row[k] for k in ('minimum_seconds', 'maximum_seconds')}
    # Amarelo e limpeza são fixos neste modo e não são ações do modelo.
    return pd.DataFrame([{'key': f"{s['tls_id']}:{s['phase_index']}",
                          'type': {'green': 'Verde', 'yellow': 'Amarelo', 'all_red': 'Intervalo de segurança'}[s['kind']],
                          'minimum_seconds': saved.get(f"{s['tls_id']}:{s['phase_index']}", {}).get('minimum_seconds', s['durations_seconds'][0]) if s['kind'] == 'green' else s['durations_seconds'][1],
                          'maximum_seconds': saved.get(f"{s['tls_id']}:{s['phase_index']}", {}).get('maximum_seconds', s['durations_seconds'][2]) if s['kind'] == 'green' else s['durations_seconds'][1]}
                         for s in specs])


def describe_phase_limits(config, rows, labels):
    if not rows:
        return []
    timings = signal_presentation(config, labels)
    targets = {t['tls_id']: t for t in config['targets']}
    result = []
    for row in rows:
        tls, index = row['key'].rsplit(':', 1)
        starts = targets[tls]['phase_indices']
        stage = max((i for i, start in enumerate(starts, 1) if start <= int(index)), default=1)
        matching = next((t for t in timings if t['controlador'] == tls and t['Grupo'] == f'Etapa {stage}'), None)
        result.append({**row, 'crossing': targets[tls]['name'],
                       'signals': matching['_controller_label'] if matching else 'Semáforos do cruzamento',
                       'stage': f'Etapa {stage}'})
    return result


def phase_limits_editor(rows, key):
    """Edita uma etapa e conserva os limites das demais ao trocar seletores."""
    columns = ['key', 'crossing', 'signals', 'stage', 'type', 'reference', 'minimum_seconds', 'maximum_seconds']
    if not rows:
        st.info('Este modo controla a abertura do verde sem editar durações por etapa.')
        return pd.DataFrame(columns=columns)
    signature = tuple((r['key'], r['reference'], r['minimum_seconds'], r['maximum_seconds']) for r in rows)
    namespace = f'{key}_{sha256(repr(signature).encode()).hexdigest()[:16]}'
    saved_key = namespace + '_values'
    saved = st.session_state.setdefault(saved_key, {})
    values = [{**row, **saved.get(row['key'], {})} for row in rows]

    def choose(label, options, suffix, format_func=str):
        widget_key = f'{namespace}_{suffix}'
        if st.session_state.get(widget_key) not in options:
            st.session_state[widget_key] = options[0]
        return st.selectbox(label, options, format_func=format_func, key=widget_key, disabled=len(options) == 1)

    crossing = choose('Cruzamento para ajustar', list(dict.fromkeys(r['crossing'] for r in values)), 'crossing')
    local = [r for r in values if r['crossing'] == crossing]
    controllers = dict((r['key'].rsplit(':', 1)[0], r['signals']) for r in local)
    controller = choose('Conjunto de semáforos para ajustar', list(controllers), f'controller_{crossing}', controllers.get)
    local = [r for r in local if r['key'].rsplit(':', 1)[0] == controller]
    stage = choose('Etapa para ajustar', list(dict.fromkeys(r['stage'] for r in local)), f'stage_{controller}')
    selected = [r for r in local if r['stage'] == stage]
    st.caption('Esta etapa reúne movimentos que recebem verde juntos. Cada linha abaixo representa um tempo da sequência: verde, amarelo ou intervalo de segurança.')
    edited = st.data_editor(pd.DataFrame(selected, columns=columns), hide_index=True,
        disabled=['key', 'crossing', 'signals', 'stage', 'type', 'reference'],
        key=f'{namespace}_editor_{controller}_{stage}',
        column_config={name: None for name in ('key', 'crossing', 'signals', 'stage')} | {
            'type': st.column_config.TextColumn('Tempo do sinal'),
            'reference': st.column_config.NumberColumn('Começa com (s)', help='Tempo inicial antes dos ajustes do algoritmo.'),
            'minimum_seconds': st.column_config.NumberColumn('Pode diminuir até (s)', min_value=.1, help='Menor duração permitida. Os mínimos do cenário continuam sendo verificados.'),
            'maximum_seconds': st.column_config.NumberColumn('Pode aumentar até (s)', min_value=.1, help='Maior duração permitida, respeitando também os tetos gerais do amarelo, do intervalo de segurança e do ciclo.'),
        })
    for row in edited.to_dict('records'):
        saved[row['key']] = {field: row[field] for field in ('minimum_seconds', 'maximum_seconds')}
    st.session_state[saved_key] = saved
    st.caption('Edite apenas os dois limites. Se forem iguais, o tempo fica fixo. As alterações são mantidas ao consultar outra etapa e entram no próximo treinamento.')
    return pd.DataFrame([{**row, **saved.get(row['key'], {})} for row in rows], columns=columns)
