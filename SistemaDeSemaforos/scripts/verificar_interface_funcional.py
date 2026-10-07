"""AppTest de reconexão, gráficos e aplicação dos arquivos importados."""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from semaforos.arquivos import write_json
from semaforos.cenario.configuracao import read_config

with tempfile.TemporaryDirectory(dir=ROOT / 'resultados', prefix='ui_test_interface_') as temporary:
    folder = Path(temporary)
    output = folder / 'execucao'
    episode = output / 'episodes' / 'episode_00001'
    episode.mkdir(parents=True)
    config = read_config(ROOT / 'config/cenario.json')
    write_json(folder / 'cenario.json', config)
    write_json(folder / 'job.json', {'status': 'running', 'command': 'run-reference', 'pid': os.getpid(),
                                   'process_created_at': psutil.Process().create_time()})
    write_json(output / 'live.json', {'episode_output': str(episode), 'simulated_seconds': 10,
        'queue_vehicles_now': 3, 'arrived': 2, 'pedestrians_arrived': 1,
        'intersections': [{'intersection': 'Cruzamento fictício do teste', 'queue_vehicle_seconds': 15}]})
    (episode / 'live_history.csv').write_text('simulated_seconds,queue_vehicles_now,arrived,pedestrians_arrived,wait_vehicle_seconds,reward_step\n5,2,1,0,10,-1\n10,3,2,1,15,-2\n', encoding='utf-8')
    (output / 'training_episodes.csv').write_text('episode,reward,episode_complete\n1,-10,True\n2,-5,False\n', encoding='utf-8')
    for _ in range(2):
        # Sessões independentes recuperam o processo sem compartilhar session_state.
        app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
        assert not app.exception, str(app.exception)
        assert Path(app.session_state['job']['folder']) == folder
        assert any(w.label == 'Fila atual nas entradas' for w in app.metric)
        assert any(w.label == 'Exportar histórico ao vivo (.csv)' for w in app.get('download_button'))
        assert len(app.get('arrow_vega_lite_chart')) >= 5
    next(w for w in app.button if w.label == 'Interromper execução').click().run()
    assert (folder / 'cancel.flag').is_file()
    write_json(folder / 'job.json', {'status': 'completed', 'command': 'run-reference', 'exit_code': 0})
    # UploadedFile é substituído só na leitura do widget; aplicação/validação usam o código real.
    counts = SimpleNamespace(name='counts.csv', file_id='counts-test', getvalue=lambda: b'edge_id,vehicles_per_hour\n1156717168,600\n')
    with patch('streamlit.file_uploader', side_effect=lambda label, **kwargs: counts if 'contagens' in label else None):
        next(w for w in app.radio if w.label == 'Modelo').set_value('Volume por via').run()
        next(w for w in app.button if w.label == 'Aplicar contagens associadas').click().run()
        assert not app.exception, str(app.exception)
        assert not app.error, str(app.error)
        semantics = next(w for w in app.radio if w.label == 'O que estes volumes representam?')
        assert semantics.value == 'Contagens observadas: calibrar entradas da rede'
        next(w for w in app.button if w.label == 'Calibrar demanda e conferir contagens').click().run()
        assert not app.error, str(app.error)
    od = SimpleNamespace(name='od.csv', file_id='od-test', getvalue=lambda: b'from_edge,to_edge,vehicles_per_hour\n1156717168,154252437#1,600\n')
    with patch('streamlit.file_uploader', side_effect=lambda label, **kwargs: od if 'OD' in label else None):
        next(w for w in app.radio if w.label == 'Modelo').set_value('Pares origem–destino').run()
        next(w for w in app.button if w.label == 'Aplicar arquivo de OD').click().run()
        assert not app.exception, str(app.exception)
        assert not app.error, str(app.error)
        assert any('154252437#1' in str(item.value.to_dict('records')) for item in app.dataframe)
print('AppTest: reconexão em duas sessões, quatro gráficos ao vivo, curva de episódios, cancelamento e importações aprovados.')
