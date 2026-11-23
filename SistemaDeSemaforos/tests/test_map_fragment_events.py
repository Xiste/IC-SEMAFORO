"""Exercita os eventos reais do servidor Streamlit, sem iniciar SUMO/treinamento."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import pyarrow as pa

from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from semaforos.caminhos import PROJECT_ROOT


def test_map_selection_is_partial_and_latest_edits_reach_execution(tmp_path):
    source = tmp_path / 'fragment_app.py'
    captured = tmp_path / 'captured.json'
    source.write_text(f'''
import json, runpy
from pathlib import Path
import streamlit as st
import semaforos.cenario.ciclos as cycles
import semaforos.experimentos.tarefas as tasks
st.session_state['full_app_passes'] = st.session_state.get('full_app_passes', 0) + 1
def capture(config, command, results, model=None):
    Path({str(captured)!r}).write_text(json.dumps(config, default=str), encoding='utf-8')
    return tasks.job_paths({str(tmp_path / 'fake_execution')!r})
tasks.start_job = capture
tasks.saved_jobs = lambda results: []
write_network = cycles.save_adjusted_network
cycles.save_adjusted_network = lambda config, edits, directory: write_network(config, edits, {str(tmp_path / 'edited_networks')!r})
runpy.run_path({str(PROJECT_ROOT / 'interface.py')!r}, run_name='__main__')
st.caption('FULL_APP_PASS_MARKER:' + str(st.session_state['full_app_passes']))
''', encoding='utf-8')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    isolated = PROJECT_ROOT / '.venv-verificacao/Scripts/python.exe'
    python = str(isolated) if isolated.exists() else sys.executable
    environment = {**os.environ, 'PYTHONPATH': str(PROJECT_ROOT)}
    with (tmp_path / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([python, '-m', 'streamlit', 'run', str(source),
            '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
            '--server.fileWatcherType=none', '--browser.gatherUsageStats=false'],
            cwd=PROJECT_ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1).close()
                    break
                except OSError:
                    assert process.poll() is None, (tmp_path / 'server.log').read_text(encoding='utf-8')
                    assert time.monotonic() < deadline, 'Servidor de teste nao iniciou'
                    time.sleep(.1)
            asyncio.run(_exercise_events(port, captured))
        finally:
            process.terminate()
            process.wait(timeout=15)


async def _exercise_events(port, captured):
    connection = await websocket_connect(HTTPRequest(f'ws://127.0.0.1:{port}/_stcore/stream',
        headers={'Origin': f'http://127.0.0.1:{port}'}), subprotocols=['streamlit'], max_message_size=32*1024*1024)
    states = {}
    async def rerun(fragment=''):
        request = BackMsg()
        request.rerun_script.fragment_id = fragment
        for widget_id, (field, value) in states.items():
            widget = request.rerun_script.widget_states.widgets.add(id=widget_id)
            setattr(widget, field, value)
        start = time.perf_counter()
        await connection.write_message(request.SerializeToString(), binary=True)
        messages = []
        while True:
            raw = await asyncio.wait_for(connection.read_message(), timeout=90)
            assert raw is not None, 'Servidor encerrou a sessao'
            message = ForwardMsg.FromString(raw)
            messages.append(message)
            if (message.WhichOneof('type') == 'script_finished'
                    and message.script_finished != ForwardMsg.FINISHED_EARLY_FOR_RERUN):
                break
        exceptions = [m.delta.new_element.exception.message for m in messages
                      if m.WhichOneof('type') == 'delta' and m.delta.new_element.HasField('exception')]
        assert not exceptions, exceptions
        return messages, time.perf_counter() - start
    def elements(messages, kind):
        return [(m, getattr(m.delta.new_element, kind)) for m in messages
                if m.WhichOneof('type') == 'delta' and m.delta.new_element.HasField(kind)]
    def dialogs(messages):
        return [(m, m.delta.add_block.dialog) for m in messages
                if m.WhichOneof('type') == 'delta' and m.delta.add_block.HasField('dialog')]

    def tab_labels(messages):
        return {m.delta.add_block.tab.label for m in messages
                if m.WhichOneof('type') == 'delta' and m.delta.add_block.HasField('tab')}

    def search_has_crossings(messages):
        return any(option.startswith('Travessias · ')
                   for _, widget in elements(messages, 'selectbox') if widget.label == 'Buscar rua ou cruzamento no mapa'
                   for option in widget.options)
    try:
        initial, full_time = await rerun()
        first_message, chart = elements(initial, 'deck_gl_json_chart')[0]
        fragment = first_message.delta.fragment_id
        assert fragment, 'Mapa precisa pertencer ao fragmento de configuracao'
        initial_view = json.loads(chart.json)['initialViewState']
        layers = {layer['id']: layer['data'] for layer in json.loads(chart.json)['layers']}
        roads = layers['configuration-roads']
        assert not layers['configuration-pedestrians']
        assert not any(p.label.startswith('Variar o fluxo') for _, p in elements(initial, 'checkbox'))
        assert not search_has_crossings(initial)
        assert {'Mapa', 'Tabela', 'Volumes das vias', 'Tempos dos semáforos'} <= tab_labels(initial)
        assert 'Travessias' not in tab_labels(initial)
        assert all(feature['geometry']['geometries'][1]['coordinates']
                   for feature in layers['configuration-signals'])
        timings = []
        first_rate_id = None
        # Primeiro clique e troca de via devem manter identidade/caminho do canvas.
        for index in (0, 1, 0):
            states[chart.id] = ('string_value', json.dumps({'selection': {
                'indices': {'configuration-roads': [index]},
                'objects': {'configuration-roads': [roads[index]]}}}))
            partial, elapsed = await rerun(fragment)
            timings.append(elapsed)
            assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(partial, 'markdown'))
            updated_message, updated_chart = elements(partial, 'deck_gl_json_chart')[0]
            assert updated_chart.id == chart.id
            assert list(updated_message.metadata.delta_path) == list(first_message.metadata.delta_path)
            assert json.loads(updated_chart.json)['initialViewState'] == initial_view
            rate_message, rate = next((m, p) for m, p in elements(partial, 'number_input') if p.label == 'Veículos por hora')
            assert rate_message.delta.fragment_id and rate_message.delta.fragment_id != fragment
            if index == 0 and len(timings) == 1:
                first_rate_id = rate.id
                states[rate.id] = ('double_value', 600.)
                edited, _ = await rerun(rate_message.delta.fragment_id)
                assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(edited, 'markdown'))
            elif len(timings) == 3:
                # O valor vigente pode ficar no WidgetState sem repetir value/default
                # no delta. A persistencia do numero e conferida no payload abaixo.
                assert rate.id == first_rate_id
        close_message, close = next((m, p) for m, p in elements(partial, 'button') if p.label == 'Fechar ajustes')
        assert close_message.delta.fragment_id == fragment
        states[close.id] = ('trigger_value', True)
        closed, close_time = await rerun(fragment)
        states.pop(close.id)
        assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(closed, 'markdown'))
        assert dialogs(closed)[-1][1].is_open is False
        closed_message, closed_chart = elements(closed, 'deck_gl_json_chart')[0]
        assert closed_chart.id == chart.id
        assert list(closed_message.metadata.delta_path) == list(first_message.metadata.delta_path)
        assert not any(p.label.startswith('Reabrir ajustes:') for _, p in elements(closed, 'button'))
        states[chart.id] = ('string_value', json.dumps({'selection': {
            'indices': {'configuration-roads': [0]},
            'objects': {'configuration-roads': [{**roads[0], 'color': [0, 0, 0]}]},
        }}))
        replayed, _ = await rerun(fragment)
        assert not any(p.label == 'Veículos por hora' for _, p in elements(replayed, 'number_input'))
        # O mapa alterna a seleção ao clicar outra vez no mesmo objeto.
        states[chart.id] = ('string_value', json.dumps({'selection': {'indices': {}, 'objects': {}}}))
        unselected, _ = await rerun(fragment)
        assert not any(p.label == 'Veículos por hora' for _, p in elements(unselected, 'number_input'))
        states[chart.id] = ('string_value', json.dumps({'selection': {
            'indices': {'configuration-roads': [0]}, 'objects': {'configuration-roads': [roads[0]]},
        }}))
        reopened, _ = await rerun(fragment)
        assert any(p.label == 'Veículos por hora' for _, p in elements(reopened, 'number_input'))
        dialog_message, dialog = dialogs(reopened)[-1]
        assert dialog.is_open and dialog_message.delta.fragment_id == fragment
        states[dialog.id] = ('trigger_value', True)
        dismissed, dismiss_time = await rerun(fragment)
        states.pop(dialog.id)
        assert dialogs(dismissed)[-1][1].is_open is False
        assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(dismissed, 'markdown'))
        # O ícone e os corredores pertencem ao mesmo objeto selecionável.
        signal_index, signal = next((i, p) for i, p in enumerate(layers['configuration-signals'])
                                    if p['tls_id'] == 'FAM_RONDON_PARANA')
        assert signal['type'] == 'Feature'
        assert signal['affected_edges']
        assert signal['geometry']['geometries'][1]['coordinates']
        states[chart.id] = ('string_value', json.dumps({'selection': {
            'indices': {'configuration-signals': [signal_index]},
            'objects': {'configuration-signals': [signal]}}}))
        signal_selected, _ = await rerun(fragment)
        assert elements(signal_selected, 'deck_gl_json_chart')[0][1].id == chart.id
        assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(signal_selected, 'markdown'))
        assert not any(p.label == 'Movimento no ciclo' for _, p in elements(signal_selected, 'selectbox'))
        assert not any(p.label == 'Ver um ciclo completo no SUMO' for _, p in elements(signal_selected, 'button'))
        stages = next(p for _, p in elements(signal_selected, 'selectbox') if p.label == 'Quem recebe verde')
        assert list(stages.options) == [
            'Rua Paraná → sudeste',
            'Av. Rondon Pacheco nos dois sentidos + Rua Paraná → noroeste',
        ]
        new_times = []
        for label in ('Verde (s)', 'Amarelo (s)', 'Todos em vermelho (s)'):
            value = next(p for _, p in elements(signal_selected, 'number_input') if p.label == label)
            new_times.append(value.default + 1)
            states[value.id] = ('double_value', new_times[-1])
        submit_message, submit = next((m, p) for m, p in elements(signal_selected, 'button') if p.label == 'Aplicar tempos')
        states[submit.id] = ('trigger_value', True)
        applied, _ = await rerun(submit_message.delta.fragment_id)
        states.pop(submit.id)
        assert any('Tempos aplicados' in p.body for _, p in elements(applied, 'alert'))
        signal_close = next(p for _, p in elements(signal_selected, 'button') if p.label == 'Fechar ajustes')
        states[signal_close.id] = ('trigger_value', True)
        signal_closed, _ = await rerun(fragment)
        states.pop(signal_close.id)

        for label, crossing in (
                ('Cruzamento das vias', roads[0]['crossing']),
                ('Cruzamento dos semáforos', signal['crossing'])):
            select = next(p for _, p in elements(signal_closed, 'selectbox') if p.label == label)
            assert crossing in select.options
            states[select.id] = ('string_value', crossing)
        tables, _ = await rerun(fragment)

        async def apply_table(messages, label, column, updates):
            editor = next(p for _, p in elements(messages, 'arrow_data_frame')
                          if p.id and column in pa.ipc.open_stream(p.data).read_all().column_names)
            submit = next(p for _, p in elements(messages, 'button') if p.label == label)
            states[editor.id] = ('string_value', json.dumps({
                'edited_rows': updates, 'added_rows': [], 'deleted_rows': [],
            }))
            states[submit.id] = ('trigger_value', True)
            result, _ = await rerun(fragment)
            states.pop(editor.id)
            states.pop(submit.id)
            return result

        def table_frame(messages, column):
            return next(frame for _, editor in elements(messages, 'arrow_data_frame') if editor.id
                        for frame in [pa.ipc.open_stream(editor.data).read_all().to_pandas()] if column in frame)

        road_ref = roads[0]['title'].split(' · ')[0]
        road_rows = table_frame(tables, 'Veículos por hora')
        road_index = road_rows.index[road_rows['Entrada'] == road_ref][0]
        assert road_rows.loc[road_index, 'Veículos por hora'] == 600.
        road_applied = await apply_table(tables, 'Aplicar volumes da tabela', 'Veículos por hora',
                                         {int(road_index): {'Veículos por hora': 720.}})
        assert any('Volumes aplicados' in p.body for _, p in elements(road_applied, 'alert'))
        signal_rows = table_frame(tables, 'Todos em vermelho (s)')
        group = 'Conjunto ' + signal['description'].split(' · ')[0].split()[-1]
        signal_index_in_table = signal_rows.index[(signal_rows['Semáforo'] == group)
                                                  & (signal_rows['Quem recebe verde'] == stages.options[0])][0]
        assert signal_rows.loc[signal_index_in_table, 'Verde (s)'] == new_times[0]
        new_times[0] += 1
        signal_applied = await apply_table(road_applied, 'Aplicar tempos da tabela', 'Todos em vermelho (s)',
                                           {int(signal_index_in_table): {'Verde (s)': new_times[0]}})
        assert any('Tempos aplicados' in p.body for _, p in elements(signal_applied, 'alert'))

        states[chart.id] = ('string_value', json.dumps({'selection': {
            'indices': {'configuration-roads': [0]}, 'objects': {'configuration-roads': [roads[0]]},
        }}))
        reopened, _ = await rerun(fragment)
        rate = next(p for _, p in elements(reopened, 'number_input') if p.label == 'Veículos por hora')
        assert (rate.value if rate.set_value else rate.default) == 720.
        close_message, close = next((m, p) for m, p in elements(reopened, 'button') if p.label == 'Fechar ajustes')
        states[close.id] = ('trigger_value', True)
        await rerun(close_message.delta.fragment_id)
        states.pop(close.id)

        toggle = next(p for _, p in elements(initial, 'checkbox') if p.label == 'Incluir pedestres?')
        states[toggle.id] = ('bool_value', True)
        enabled, _ = await rerun(fragment)
        enabled_chart = elements(enabled, 'deck_gl_json_chart')[0][1]
        crossings = next(layer['data'] for layer in json.loads(enabled_chart.json)['layers']
                         if layer['id'] == 'configuration-pedestrians')
        assert search_has_crossings(enabled)
        assert 'Travessias' in tab_labels(enabled)
        pedestrian_select = next(p for _, p in elements(enabled, 'selectbox')
                                 if p.label == 'Cruzamento para preencher os pedestres')
        states[pedestrian_select.id] = ('string_value', crossings[0]['crossing'])
        crossing_event = ('string_value', json.dumps({'selection': {
            'indices': {'configuration-pedestrians': [0]},
            'objects': {'configuration-pedestrians': [crossings[0]]},
        }}))
        states[enabled_chart.id] = crossing_event
        crossing_selected, _ = await rerun(fragment)
        edit_message, pedestrian_editor = next((m, p) for m, p in elements(crossing_selected, 'arrow_data_frame')
                                                if p.id and 'persons_per_hour' in p.columns
                                                and m.delta.fragment_id != fragment)
        states[pedestrian_editor.id] = ('string_value', json.dumps({
            'edited_rows': {'0': {'persons_per_hour': 60}}, 'added_rows': [], 'deleted_rows': [],
        }))
        await rerun(edit_message.delta.fragment_id)
        states.pop(pedestrian_editor.id)
        states[toggle.id] = ('bool_value', False)
        disabled, _ = await rerun(fragment)
        disabled_chart = elements(disabled, 'deck_gl_json_chart')[0][1]
        assert not next(layer['data'] for layer in json.loads(disabled_chart.json)['layers']
                        if layer['id'] == 'configuration-pedestrians')
        assert not search_has_crossings(disabled)
        assert 'Travessias' not in tab_labels(disabled)
        assert not any(p.label == 'Fechar ajustes' for _, p in elements(disabled, 'button'))
        states.pop(enabled_chart.id)
        states[toggle.id] = ('bool_value', True)
        visible_again, _ = await rerun(fragment)
        states[elements(visible_again, 'deck_gl_json_chart')[0][1].id] = crossing_event
        crossing_reopened, _ = await rerun(fragment)
        editor = next(p for m, p in elements(crossing_reopened, 'arrow_data_frame')
                      if p.id and 'persons_per_hour' in p.columns and m.delta.fragment_id != fragment)
        assert pa.ipc.open_stream(editor.data).read_all()['persons_per_hour'][0].as_py() == 60.
        close = next(p for _, p in elements(crossing_reopened, 'button') if p.label == 'Fechar ajustes')
        states[close.id] = ('trigger_value', True)
        pedestrian_table, _ = await rerun(fragment)
        states.pop(close.id)
        pedestrian_rows = table_frame(pedestrian_table, 'persons_per_hour')
        crossing_entry = int(pedestrian_rows.index[pedestrian_rows['persons_per_hour'] == 60.][0])
        applied_flows = await apply_table(pedestrian_table, 'Aplicar fluxos das travessias', 'persons_per_hour',
                                         {crossing_entry: {'persons_per_hour': 90.}})
        assert any('Fluxos de pedestres aplicados' in p.body for _, p in elements(applied_flows, 'alert'))
        current_chart = elements(applied_flows, 'deck_gl_json_chart')[0][1]
        states[current_chart.id] = ('string_value', json.dumps({'selection': {'indices': {}, 'objects': {}}}))
        await rerun(fragment)
        states[current_chart.id] = crossing_event
        with_updated_volume, _ = await rerun(fragment)
        editor = next(p for m, p in elements(with_updated_volume, 'arrow_data_frame')
                      if p.id and 'persons_per_hour' in p.columns and m.delta.fragment_id != fragment)
        assert pa.ipc.open_stream(editor.data).read_all()['persons_per_hour'][0].as_py() == 90.

        # Acao fora do fragmento deve usar os valores recentes, com executor substituido.
        reference = next(p for _, p in elements(initial, 'button') if p.label == 'Simular com os tempos iniciais')
        assert not reference.disabled
        states[reference.id] = ('trigger_value', True)
        await rerun()
        payload = json.loads(captured.read_text(encoding='utf-8'))
        assert payload['demand']['mode'] == 'edge_volumes'
        assert next(r['vehicles_per_hour'] for r in payload['demand']['edge_volumes'] if r['from_edge'] == roads[0]['edge_id']) == 720.
        assert len({t['name'] for t in payload['targets']}) == 9
        assert 'time_profile' not in payload['demand']
        from semaforos.cenario.rede import network_programs
        assert [phase['duration'] for phase in network_programs(payload['network'])[signal['tls_id']][:3]] == new_times
        assert payload['pedestrians']['enabled']
        assert [row['persons_per_hour'] for row in payload['pedestrians']['flows']] == [90.]
        print(f'Primeira abertura: {full_time:.3f}s; cliques parciais: ' + ', '.join(f'{t:.3f}s' for t in timings))
        print(f'Fechamento no fragmento: botão {close_time:.3f}s; X {dismiss_time:.3f}s')
    finally:
        connection.close()
