"""AppTest dos novos comandos, período de contagens e painel de diagnóstico."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from semaforos.arquivos import write_json
from semaforos.cenario.configuracao import read_config
from semaforos.experimentos.tarefas import job_paths
from semaforos.relatorios.diagnostico import export_diagnostics


with tempfile.TemporaryDirectory(dir=ROOT / 'resultados', prefix='ui_diag_') as temporary:
    folder = Path(temporary)
    output = folder / 'execucao'
    output.mkdir()
    rows = []
    for seed in (101, 102, 103):
        for controller in ('network_reference', 'queue_actuated'):
            better = controller == 'queue_actuated'
            rows.append({'controller': controller, 'seed': seed, 'episode_complete': True,
                         'simulated_seconds': 600, 'demand_sha256': f'test_{seed}', 'arrived': 50,
                         'unfinished': 10, 'pending_departure': 0, 'collision_vehicles': 0,
                         'teleports_started': 0, 'planned_pedestrians': 0,
                         'wait_vehicle_seconds': 50 if better else 100,
                         'global_halted_vehicle_seconds': 50 if better else 100})
    report = export_diagnostics(output, pd.DataFrame(rows), {'evaluation_config': {'demand': {'mode': 'random'}}})
    write_json(output / 'summary.json', {'diagnostico': report})
    write_json(folder / 'job.json', {'status': 'completed', 'command': 'compare-baselines', 'exit_code': 0})
    write_json(folder / 'cenario.json', read_config(ROOT / 'config/cenario.json'))
    app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
    next(w for w in app.selectbox if w.label == 'Execução para acompanhar').set_value(str(folder)).run()
    assert not app.exception, str(app.exception)
    assert any('Melhoria consistente' in w.value for w in app.success)
    assert any(w.label == 'Exportar melhorias.csv' for w in app.get('download_button'))
    counts = SimpleNamespace(name='counts.csv', file_id='period-test', getvalue=lambda:
        b'edge_id,vehicles,hora_inicio,hora_fim\n1156717168,10,2026-06-26 08:00:00,2026-06-26 08:01:00\n1156717168,20,2026-06-26 08:01:00,2026-06-26 08:02:00\n')
    with patch('streamlit.file_uploader', side_effect=lambda label, **kwargs: counts if 'contagens' in label else None):
        next(w for w in app.radio if w.label == 'Modelo').set_value('Volume por via').run()
        next(w for w in app.checkbox if w.label == 'Selecionar período das contagens').check().run()
        next(w for w in app.text_input if w.label.startswith('Início da medição')).set_value('2026-06-26 08:01:00').run()
        next(w for w in app.button if w.label == 'Aplicar contagens associadas').click().run()
        assert not app.exception, str(app.exception)
        assert not app.error, str(app.error)
        source_keys = [k for k in app.session_state.filtered_state if k.startswith('counts_source_')]
        assert source_keys
        assert app.session_state[source_keys[0]]['selected_rows'] == 1
        with patch('semaforos.experimentos.tarefas.start_job', return_value=job_paths(folder)) as launch:
            next(w for w in app.button if w.label == 'Validar demanda calibrada no SUMO').click().run()
            assert launch.call_args.args[1] == 'validate-demand'
            assert launch.call_args.args[0]['demand']['edge_volumes'][0]['vehicles_per_hour'] == 1200
            next(w for w in app.button if w.label == 'Comparar referência e controle por filas sem treinamento').click().run()
            assert launch.call_args.args[1] == 'compare-baselines'
            assert not app.exception, str(app.exception)
print('AppTest: período, fonte, botões de validação/comparação e painel de melhoria aprovados.')
