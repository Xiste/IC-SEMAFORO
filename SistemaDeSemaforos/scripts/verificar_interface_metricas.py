"""Novos controles da interface; tarefas são substituídas, sem SUMO/modelos."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import streamlit as st
from streamlit.testing.v1 import AppTest
from semaforos.experimentos.tarefas import job_paths
from semaforos.arquivos import write_json

with tempfile.TemporaryDirectory(dir=ROOT / 'resultados', prefix='ui_metrics_') as temporary:
    folder = Path(temporary)
    write_json(folder / 'job.json', {'status': 'completed', 'command': 'run-study', 'exit_code': 0})
    (folder / 'execucao').mkdir()
    with patch('semaforos.experimentos.tarefas.start_job', return_value=job_paths(folder)) as launch:
        app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
        assert not app.exception, str(app.exception)
        next(w for w in app.number_input if w.label == 'Aquecimento sem atuação do algoritmo (s)').set_value(60.0).run()
        next(w for w in app.checkbox if w.label == 'Escolher início e fim da janela de medição').check().run()
        next(w for w in app.number_input if w.label == 'Início da medição (s)').set_value(120.0).run()
        next(w for w in app.number_input if w.label == 'Fim da medição (s)').set_value(300.0).run()
        next(w for w in app.radio if w.label == 'Modelo').set_value('Volume por via').run()
        original_editor = st.data_editor
        def edited(data, *args, **kwargs):
            if str(kwargs.get('key', '')).startswith('intersection_totals_'):
                data = data.copy()
                data.loc[data.index[0], 'vehicles_per_hour'] = 600.0
            return original_editor(data, *args, **kwargs)
        with patch('streamlit.data_editor', side_effect=edited):
            app.run()
            next(w for w in app.button if w.label == 'Aplicar volumes por cruzamento').click().run()
        assert not app.exception, str(app.exception)
        source = next(value for key, value in app.session_state.filtered_state.items() if key.startswith('counts_source_'))
        assert source['input_method'] == 'intersection_totals'
        imported = next(value for key, value in app.session_state.filtered_state.items() if key.startswith('imported_counts_'))
        assert abs(sum(r['vehicles_per_hour'] for r in imported) - 600) < 1e-6
        next(w for w in app.button if w.label == 'Executar treinos e avaliações repetidos').click().run()
        assert launch.call_count == 1
        config, command = launch.call_args.args[:2]
        assert command == 'run-study'
        assert config['measurement'] == {'warmup_seconds': 60.0, 'start_seconds': 120.0, 'end_seconds': 300.0}, repr(config['measurement'])
        assert config['study']['training_seeds'] == [11, 22, 33]
        assert config['metrics']['collect_extended']
        assert config['metrics']['collect_vehicle_classes']
        assert not app.exception, str(app.exception)

map_app = AppTest.from_string('''
from semaforos.apresentacao.gargalos import render_bottlenecks
render_bottlenecks({'bottlenecks': [{'controller': 'PPO', 'intersection': 'A', 'status': 'Melhorou',
    'longitude': -43.1, 'latitude': -22.9, 'mean_queue_vehicle_seconds': 50,
    'peak_halted_vehicles': 2, 'color': [40,160,80,200]}]}, 'test')
''').run()
assert not map_app.exception, str(map_app.exception)
assert any(w.label == 'Controle exibido no mapa' for w in map_app.selectbox)
assert len(map_app.get('deck_gl_json_chart')) == 1
print('AppTest aprovado: janela, volumes por cruzamento, classes, botão de estudo e mapa; nenhuma tarefa real iniciada.')
