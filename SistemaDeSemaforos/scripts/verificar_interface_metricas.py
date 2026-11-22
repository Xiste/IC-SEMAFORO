"""Novos controles da interface; tarefas são substituídas, sem SUMO/modelos."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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
        app.session_state['experimental_config'] = {
            **app.session_state['experimental_config'],
            'measurement': {'warmup_seconds': 60., 'start_seconds': 60., 'end_seconds': 600.},
        }
        next(w for w in app.radio if w.label == 'Por quanto tempo simular?').set_value('300 s').run()
        layers = json.loads(app.get('deck_gl_json_chart')[0].proto.json)['layers']
        roads = next(layer['data'] for layer in layers if layer['id'] == 'configuration-roads')
        entry = next(road['edge_id'] for road in roads if road['controllers'])
        next(w for w in app.selectbox if w.label == 'Buscar rua ou cruzamento no mapa').select(entry).run()
        next(w for w in app.number_input if w.label == 'Veículos por hora').set_value(600.).run()
        next(w for w in app.checkbox if w.label == 'Coletar análise detalhada').set_value(True).run()
        next(w for w in app.button if w.label == 'Executar treinos e avaliações repetidos').click().run()
        assert not app.exception, str(app.exception)
        assert launch.call_count == 1
        config, command = launch.call_args.args[:2]
        assert command == 'run-study'
        assert config['demand']['mode'] == 'edge_volumes'
        assert config['demand']['synthetic'] is True
        assert sum(r['vehicles_per_hour'] for r in config['demand']['edge_volumes']) == 600
        assert config['measurement'] == {'warmup_seconds': 60.0, 'start_seconds': 60.0, 'end_seconds': 300.0}, repr(config['measurement'])
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
print('AppTest aprovado: janela, volumes por entrada, classes, botão de estudo e mapa; nenhuma tarefa real iniciada.')
