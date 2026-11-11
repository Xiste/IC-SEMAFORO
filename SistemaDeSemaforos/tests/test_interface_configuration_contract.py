"""Confere dados editados na UI contra o payload real entregue ao executor."""
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import sumolib
from streamlit.testing.v1 import AppTest

from semaforos.arquivos import write_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.pedestres import crossing_routes
from semaforos.cenario.demanda import create_edge_volume_demand
from semaforos.experimentos.tarefas import job_paths
from semaforos.experimentos.tarefas import start_job as persist_job, LOCAL_PROCESSES
from semaforos.arquivos import read_json


def widget(app, kind, label):
    return next(w for w in getattr(app, kind) if w.label == label)


def edit_table(app, token, edits):
    key = next(k for k, v in app.session_state.filtered_state.items()
               if token in k and isinstance(v, dict) and 'edited_rows' in v)
    app.session_state[key] = {'edited_rows': edits, 'added_rows': [], 'deleted_rows': []}
    app.run()
    assert not app.exception, app.exception


def pick_map(app, layer, field, value):
    from semaforos.apresentacao.mapa_configuracao import apply_map_selection
    chart = app.get('deck_gl_json_chart')[0]
    layers = {row['id']: row['data'] for row in json.loads(chart.proto.json)['layers']}
    geometry = {key: layers[layer_id] for key, layer_id in (
        ('signals', 'configuration-signals'), ('roads', 'configuration-roads'), ('pedestrians', 'configuration-pedestrians'))}
    namespace = next(k.rsplit('_chart_', 1)[0] for k in app.session_state.filtered_state if '_chart_' in k)
    revision = app.session_state.filtered_state.get('configuration_revision', 0)
    apply_map_selection(app.session_state, namespace, geometry, {'selection': {'objects': {layer: [{field: value}]}}},
                        demand_mode_key=f'configuration_{revision}_Como deseja informar o tráfego?')
    app.run()
    assert not app.exception, app.exception


def test_form_payload_persistence_errors_and_reload():
    config = read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json')
    from semaforos.cenario.experimental import prepare_or_reuse
    config, _, _ = prepare_or_reuse(config, PROJECT_ROOT / 'resultados')
    config['targets'].sort(key=lambda t: t['tls_id'] != 'FAM_RONDON_PARANA')
    net = sumolib.net.readNet(str(config['network']))
    entries = sorted({a.getEdge().getID() for a, _, _ in net.getTLS(config['targets'][0]['tls_id']).getConnections()
                      if a.getEdge().allows('passenger')})
    config['duration_seconds'] = 300
    config['demand'] = {'mode': 'edge_volumes', 'edge_volumes': [
        {'from_edge': edge, 'vehicles_per_hour': 360., 'to_edge': ''} for edge in entries],
        'time_profile': [{'begin': 75 * i, 'end': 75 * (i + 1), 'multiplier': 1.} for i in range(4)]}
    routes = crossing_routes(config['network'], config['targets'])
    config['pedestrians'] = {'enabled': True, 'walking_speed_meters_per_second': .8,
                            'flows': [dict(r, persons_per_hour=60.) for r in routes]}
    config = json.loads(json.dumps(config, default=str))
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'resultados', prefix='ui_contract_') as temporary:
        folder = Path(temporary)
        write_json(folder / 'job.json', {'status': 'completed', 'command': 'rl-train', 'exit_code': 0})
        write_json(folder / 'cenario.json', config)
        paths = job_paths(folder)
        with patch('semaforos.experimentos.tarefas.start_job', return_value=paths) as launch:
            app = AppTest.from_file(str(PROJECT_ROOT / 'interface.py'), default_timeout=60)
            app.session_state['loaded_config'] = config
            app.session_state['job'] = paths
            app.run()
            assert not app.exception, app.exception
            pick_map(app, 'configuration-roads', 'edge_id', entries[0])
            widget(app, 'number_input', 'Veículos por hora').set_value(650.).run()
            pick_map(app, 'configuration-pedestrians', 'crossing_id', routes[0]['crossing_id'])
            edit_table(app, '_values_', {0: {'persons_per_hour': 120.}})
            pick_map(app, 'configuration-signals', 'tls_id', config['targets'][0]['tls_id'])
            widget(app, 'number_input', 'Verde mínimo (s)').set_value(20.).run()
            widget(app, 'number_input', 'Verde máximo (s)').set_value(60.).run()
            # Invalid draft must not stop rendering or clear other edits.
            edit_table(app, '_table_', {0: {'share': 40.}})
            assert widget(app, 'button', 'Iniciar treinamento').disabled
            assert any('100%' in w.value for w in app.error)
            assert any(w.label == 'Objetivo do treinamento' for w in app.selectbox)
            edit_table(app, '_table_', {0: {'share': 40.}, 1: {'share': 10.}, 2: {'share': 20.}, 3: {'share': 30.}})
            # Switch input and visible section without losing values.
            pick_map(app, 'configuration-roads', 'edge_id', entries[1])
            assert widget(app, 'number_input', 'Veículos por hora').value == 360.
            pick_map(app, 'configuration-roads', 'edge_id', entries[0])
            assert widget(app, 'number_input', 'Veículos por hora').value == 650.
            widget(app, 'radio', 'Etapas do estudo').set_value('3 · Treinamento').run()
            widget(app, 'number_input', 'Quantidade de decisões para treinar').set_value(4096).run()
            widget(app, 'button', 'Iniciar treinamento').click().run()
            assert not app.exception, app.exception
            launch.assert_called_once()
            payload, command = launch.call_args.args[:2]
            assert command == 'rl-train'
            assert len({t['name'] for t in payload['targets']}) == 9
            assert len(payload['targets']) == 17
            rates = {r['from_edge']: r['vehicles_per_hour'] for r in payload['demand']['edge_volumes']}
            assert rates[entries[0]] == 650.
            assert all(rates[e] == 360. for e in entries[1:])
            assert all(v == 0 for e, v in rates.items() if e not in entries)
            profile = payload['demand']['time_profile']
            mass = [(r['end'] - r['begin']) * r['multiplier'] for r in profile]
            assert mass == [40., 10., 20., 30.]
            assert payload['pedestrians']['flows'][0]['persons_per_hour'] == 120.
            assert all(r['persons_per_hour'] == 60. for r in payload['pedestrians']['flows'][1:])
            first = f"{config['targets'][0]['tls_id']}:0"
            assert payload['control']['phase_duration_bounds'][first] == {'minimum_seconds': 20., 'maximum_seconds': 60.}
            assert payload['ppo']['total_timesteps'] == 4096
            # Verify the preview against actual generated trips, not only a copied formula.
            demand_output = folder / 'demand'
            demand_output.mkdir()
            routes_file = create_edge_volume_demand(payload, net, demand_output, 11)
            departures = [float(r.get('depart')) for r in ET.parse(routes_file).getroot().findall('trip')]
            generated = [sum(r['begin'] <= t < r['end'] for t in departures) for r in profile]
            preview = next(w.value for w in app.dataframe if 'share' in w.value.columns)
            assert preview['vehicles'].tolist() == generated
            with patch('semaforos.experimentos.tarefas.subprocess.Popen') as process:
                written = persist_job(payload, 'rl-train', folder / 'jobs')
                process.assert_called_once()
                assert read_json(written['folder'] / 'cenario.json') == payload
                LOCAL_PROCESSES.pop(str(written['folder']), None)
            # Same network loaded again must take saved defaults, not old drafts.
            app.session_state['experimental_config'] = {'targets': []}
            app.session_state['experimental_rows'] = []
            widget(app, 'button', 'Carregar configurações desta execução').click().run()
            assert not app.exception, app.exception
            assert len(app.session_state['experimental_config']['targets']) == 17
            assert widget(app, 'number_input', 'Quantidade de decisões para treinar').value == config['ppo']['total_timesteps']
            pick_map(app, 'configuration-roads', 'edge_id', entries[0])
            assert widget(app, 'number_input', 'Veículos por hora').value == 360.
            pick_map(app, 'configuration-pedestrians', 'crossing_id', routes[0]['crossing_id'])
            pedestrians = next(w.value for w in app.dataframe if 'persons_per_hour' in w.value.columns)
            assert pedestrians.iloc[0]['persons_per_hour'] == 60.
            periods = next(w.value for w in app.dataframe if 'share' in w.value.columns)
            assert periods['share'].tolist() == [25., 25., 25., 25.]
            pick_map(app, 'configuration-signals', 'tls_id', config['targets'][0]['tls_id'])
            assert widget(app, 'number_input', 'Verde mínimo (s)').value == config['control']['phase_duration_bounds'][first]['minimum_seconds']
            assert not any(w.label == 'Arquivo para baixar' for w in app.selectbox)


def test_rounding_preview_matches_per_entry_generation():
    app = AppTest.from_string('''
import streamlit as st
from semaforos.apresentacao.fluxo import flow_profile_editor
table = flow_profile_editor(300, planned_vehicles=4, entry_counts=[1, 1, 1, 1])
st.session_state.profile = table.to_dict('records')
''').run()
    assert not app.exception
    assert app.dataframe[0].value['vehicles'].tolist() == [0, 4, 0, 0]


def test_loaded_individual_scenario_is_expanded_without_changing_original():
    config = read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json')
    with patch('semaforos.experimentos.tarefas.start_job') as launch:
        app = AppTest.from_file(str(PROJECT_ROOT / 'interface.py'), default_timeout=90)
        app.session_state['loaded_config'] = config
        app.run()
        assert not app.exception, app.exception
        assert all('veículo' in w.value.casefold() or 'volume' in w.value.casefold() or 'entrada' in w.value.casefold()
                   for w in app.error), app.error
        assert not any(w.label == 'Como deseja informar o tráfego?' for w in app.radio)
        assert not any(w.label == 'Volume total (veículos/h)' for w in app.number_input)
        assert not any(w.label == 'Cruzamentos controlados' for w in app.radio)
        assert not any(w.label == 'Qual cruzamento?' for w in app.selectbox)
        assert len({t['name'] for t in app.session_state['experimental_config']['targets']}) == 9
        assert len(app.session_state['experimental_config']['targets']) == 17
        assert len(config['targets']) == 1
        launch.assert_not_called()


def test_errors_explain_action_without_technical_keys():
    from semaforos.apresentacao.layout import friendly_configuration_error
    for text in ('decision_seconds deve ser >= step_seconds', 'Limites PPO inválidos para t:0; mínimo 8 s',
                 'Aquecimento e limites da medição devem ser múltiplos do passo SUMO', 'invalid literal for int()'):
        message = friendly_configuration_error(ValueError(text))
        assert message and not any(key in message for key in ('decision_seconds', 'step_seconds', 'PPO', 'int()'))
