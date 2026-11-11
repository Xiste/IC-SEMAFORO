"""Fluxo da interface reorganizada. Todos os inícios de tarefas são substituídos."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from semaforos.experimentos.tarefas import job_paths
from semaforos.arquivos import write_json

with tempfile.TemporaryDirectory(dir=ROOT / 'resultados', prefix='ui_fluxo_') as temporary:
    folder = Path(temporary)
    write_json(folder / 'job.json', {'status': 'completed', 'command': 'rl-train', 'exit_code': 0})
    with patch('semaforos.experimentos.tarefas.start_job', return_value=job_paths(folder)) as launch:
        app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
        assert not app.exception, str(app.exception)
        assert not any(w.label == 'Rede' for w in app.selectbox)
        assert not any(w.label == 'Cruzamentos controlados' for w in app.radio)
        assert not any(w.label == 'Qual cruzamento?' for w in app.selectbox)
        assert app.session_state['ui_default_tab'] == '2 · Tráfego'
        assert len(app.session_state['experimental_config']['targets']) == 17
        assert not any(w.label == 'Cruzamento no mapa' for w in app.selectbox)
        labels = next(w for w in app.radio if w.label == 'Etapas do estudo').options
        assert labels[:5] == ['1 · Cenário', '2 · Tráfego', '3 · Treinamento', '4 · Resultados', 'Referência técnica'], labels
        assert any(w.label == 'Configurações avançadas' for w in app.get('expander'))
        assert not any(w.label == 'Etapa para ajustar' for w in app.selectbox)
        assert next(w for w in app.button if w.label == 'Comparar PPO com os tempos iniciais').disabled
        launch.assert_not_called()
        assert not any(w.label == 'Como deseja informar o tráfego?' for w in app.radio)
        assert not app.exception, str(app.exception)
        assert not any(w.label == 'Volume total (veículos/h)' for w in app.number_input)
        assert not any(w.label == 'Usar contagens reais para calibrar o tráfego' for w in app.toggle)
        assert not list(app.get('file_uploader'))
        assert not any('OD' in w.label for w in app.get('download_button'))
        import json
        layers = json.loads(app.get('deck_gl_json_chart')[0].proto.json)['layers']
        assert len(next(l for l in layers if l['id'] == 'configuration-roads')['data']) > 34
        assert not any(w.label == 'Cruzamento para preencher os volumes' for w in app.selectbox)
        from semaforos.apresentacao.mapa_configuracao import apply_map_selection
        geometry = {key: next(l for l in layers if l['id'] == layer)['data'] for key, layer in (
            ('roads','configuration-roads'), ('signals','configuration-signals'), ('pedestrians','configuration-pedestrians'))}
        entry = next(r['edge_id'] for r in geometry['roads'] if r['controllers'])
        namespace = next(k.rsplit('_chart_',1)[0] for k in app.session_state.filtered_state if '_chart_' in k)
        apply_map_selection(app.session_state,namespace,geometry,{'selection':{'objects':{'configuration-roads':[{'edge_id':entry}]}}})
        app.run()
        next(w for w in app.number_input if w.label == 'Veículos por hora').set_value(600.).run()
        next(w for w in app.button if w.label == 'Continuar: configurar o tráfego').click().run()
        assert app.session_state['ui_default_tab'] == '2 · Tráfego'
        next(w for w in app.number_input if w.label == 'Aquecimento sem atuação do algoritmo (s)').set_value(600.0).run()
        assert next(w for w in app.button if w.label == 'Iniciar treinamento').disabled
        assert any('Não foi possível iniciar' in w.value for w in app.error)
        next(w for w in app.number_input if w.label == 'Aquecimento sem atuação do algoritmo (s)').set_value(60.0).run()
        assert next(w for w in app.number_input if w.label == 'Quantidade de decisões para treinar').value == 2048
        next(w for w in app.number_input if w.label == 'Quantidade de decisões para treinar').set_value(4096).run()
        assert not app.exception, str(app.exception)
        next(w for w in app.selectbox if w.label == 'Objetivo do treinamento').select('Diminuir as filas').run()
        next(w for w in app.button if w.label == 'Iniciar treinamento').click().run()
        launch.assert_called_once()
        config, command = launch.call_args.args[:2]
        assert command == 'rl-train'
        assert config['demand']['mode'] == 'edge_volumes'
        assert next(r['vehicles_per_hour'] for r in config['demand']['edge_volumes'] if r['from_edge'] == entry) == 600.
        assert config['experimental']['method'] == 'compatible_groups_v2'
        assert len(config['targets']) == 17
        assert config['ppo']['total_timesteps'] == 4096
        assert config['measurement']['warmup_seconds'] == 60
        assert config['control']['action_mode'] == 'adaptive_signals'
        assert config['objectives']['queues'] == 2
        assert config['demand']['synthetic'] is True
        assert app.session_state['ui_default_tab'] == '4 · Resultados'
        assert not app.exception, str(app.exception)
print('AppTest aprovado: navegacao, validacao, objetivo e treino adaptativo com inicio substituido.')
