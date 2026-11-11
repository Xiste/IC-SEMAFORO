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
import semaforos.experimentos.tarefas as tasks
st.session_state['full_app_passes'] = st.session_state.get('full_app_passes', 0) + 1
def capture(config, command, results, model=None):
    Path({str(captured)!r}).write_text(json.dumps(config, default=str), encoding='utf-8')
    return tasks.job_paths({str(tmp_path / 'fake_execution')!r})
tasks.start_job = capture
tasks.saved_jobs = lambda results: []
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
    try:
        initial, full_time = await rerun()
        first_message, chart = elements(initial, 'deck_gl_json_chart')[0]
        fragment = first_message.delta.fragment_id
        assert fragment, 'Mapa precisa pertencer ao fragmento de configuracao'
        initial_view = json.loads(chart.json)['initialViewState']
        layers = {layer['id']: layer['data'] for layer in json.loads(chart.json)['layers']}
        roads = layers['configuration-roads']
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
            assert all(m.delta.fragment_id == fragment for m in partial if m.WhichOneof('type') == 'delta')
            updated_message, updated_chart = elements(partial, 'deck_gl_json_chart')[0]
            assert updated_chart.id == chart.id
            assert list(updated_message.metadata.delta_path) == list(first_message.metadata.delta_path)
            assert json.loads(updated_chart.json)['initialViewState'] == initial_view
            rate = next(p for _, p in elements(partial, 'number_input') if p.label == 'Veículos por hora')
            if index == 0 and len(timings) == 1:
                first_rate_id = rate.id
                states[rate.id] = ('double_value', 600.)
                edited, _ = await rerun(fragment)
                assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(edited, 'markdown'))
            elif len(timings) == 3:
                # O valor vigente pode ficar no WidgetState sem repetir value/default
                # no delta. A persistencia do numero e conferida no payload abaixo.
                assert rate.id == first_rate_id
        close = next(p for _, p in elements(partial, 'button') if p.label == 'Fechar ajustes')
        states[close.id] = ('trigger_value', True)
        closed, _ = await rerun(fragment)
        states.pop(close.id)
        closed_message, closed_chart = elements(closed, 'deck_gl_json_chart')[0]
        assert closed_chart.id == chart.id
        assert list(closed_message.metadata.delta_path) == list(first_message.metadata.delta_path)
        assert any(p.label == 'Mostrar ajustes' for _, p in elements(closed, 'button'))
        # O icone e os corredores pertencem ao mesmo objeto selecionavel. A
        # tabela de tempos aparece sem recriar o mapa nem sair do fragmento.
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
        frames = [pa.ipc.open_stream(p.data).read_all().to_pandas()
                  for _, p in elements(signal_selected, 'arrow_data_frame')]
        table = next(frame for frame in frames if 'Vermelho (s)' in frame.columns)
        affected_references = {r['title'].split(' · ')[0] for r in roads if r['edge_id'] in signal['affected_edges']}
        displayed_references = set(table.loc[table['Entrada'].str.startswith('Entrada'), 'Entrada'])
        assert displayed_references == affected_references
        assert all(table[['Verde (s)','Amarelo (s)','Vermelho (s)']].sum(axis=1) > 0)
        assert any('Programa inicial da simulação' in p.body for _, p in elements(signal_selected, 'markdown'))
        # Editar periodos tambem precisa permanecer no fragmento, inclusive o
        # rerun adicional usado para atualizar as porcentagens e as estimativas.
        profile_toggle = next(p for _, p in elements(initial, 'checkbox') if p.label.startswith('Variar o fluxo'))
        states[profile_toggle.id] = ('bool_value', True)
        profile_open, _ = await rerun(fragment)
        editor = next(p for _, p in elements(profile_open, 'arrow_data_frame') if '"share"' in p.columns)
        states[editor.id] = ('string_value', json.dumps({'edited_rows': {
            str(i): {'share': share} for i, share in enumerate((40.,10.,20.,30.))},
            'added_rows': [], 'deleted_rows': []}))
        profile_changed, _ = await rerun(fragment)
        assert not any('FULL_APP_PASS_MARKER' in p.body for _, p in elements(profile_changed, 'markdown'))
        assert elements(profile_changed, 'deck_gl_json_chart')[-1][1].id == chart.id
        # Acao fora do fragmento deve usar os valores recentes, com executor substituido.
        reference = next(p for _, p in elements(initial, 'button') if p.label == 'Simular com os tempos iniciais')
        assert not reference.disabled
        states[reference.id] = ('trigger_value', True)
        await rerun()
        payload = json.loads(captured.read_text(encoding='utf-8'))
        assert payload['demand']['mode'] == 'edge_volumes'
        assert next(r['vehicles_per_hour'] for r in payload['demand']['edge_volumes'] if r['from_edge'] == roads[0]['edge_id']) == 600.
        assert len({t['name'] for t in payload['targets']}) == 9
        assert [(r['end']-r['begin'])*r['multiplier'] for r in payload['demand']['time_profile']] == [40.,10.,20.,30.]
        print(f'Primeira abertura: {full_time:.3f}s; cliques parciais: ' + ', '.join(f'{t:.3f}s' for t in timings))
    finally:
        connection.close()
