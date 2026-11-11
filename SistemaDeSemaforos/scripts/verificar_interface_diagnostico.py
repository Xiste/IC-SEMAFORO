"""AppTest dos novos comandos, período de contagens e painel de diagnóstico."""
import sys
import tempfile
from pathlib import Path
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
    assert (output / 'diagnostico.json').is_file()
    assert not any(w.label == 'Exportar melhorias.csv' for w in app.get('download_button'))
    from semaforos.cenario.importacao import parse_counts, count_period
    counts = b'edge_id,vehicles,hora_inicio,hora_fim\n1156717168,10,2026-06-26 08:00:00,2026-06-26 08:01:00\n1156717168,20,2026-06-26 08:01:00,2026-06-26 08:02:00\n'
    measured = parse_counts(counts, 'counts.csv', '2026-06-26 08:01:00', '2026-06-26 08:02:00')
    _, period = count_period(counts, 'counts.csv', '2026-06-26 08:01:00', '2026-06-26 08:02:00')
    assert period['selected_rows'] == 1
    assert measured[0]['vehicles_per_hour'] == 1200
    with patch('semaforos.experimentos.tarefas.start_job', return_value=job_paths(folder)) as launch:
        next(w for w in app.button if w.label == 'Comparar tempos iniciais com controle por filas').click().run()
        assert launch.call_args.args[1] == 'compare-baselines'
        assert not app.exception, str(app.exception)
print('AppTest: diagnostico, comparacao e suporte a contagens preservados.')
