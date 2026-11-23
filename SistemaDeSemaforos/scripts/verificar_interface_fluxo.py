"""Fluxo da interface reorganizada. Todos os inícios de tarefas são substituídos."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from semaforos.apresentacao.mapa_configuracao import apply_map_selection
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
        assert app.session_state['ui_default_tab'] == '1 · Cenário e tráfego'
        assert len(app.session_state['experimental_config']['targets']) == 17
        assert not any(w.label == 'Cruzamento no mapa' for w in app.selectbox)
        labels = next(w for w in app.radio if w.label == 'Etapas do estudo').options
        assert labels == ['1 · Cenário e tráfego', '2 · Treinamento', '3 · Resultados', 'Referência técnica'], labels
        assert not any(w.label == 'Preparar simulação' for w in app.button)
        assert not any(w.label in ('Continuar: configurar o tráfego', 'Voltar: escolher o cenário') for w in app.button)
        assert any(w.label == 'Configurações avançadas' for w in app.get('expander'))
        assert not any(w.label == 'Avançado: precisão e aquecimento' for w in app.get('expander'))
        assert not any(w.label == 'Etapa para ajustar' for w in app.selectbox)
        assert next(w for w in app.button if w.label == 'Iniciar treinamento').disabled
        launch.assert_not_called()
        assert not any(w.label == 'Como deseja informar o tráfego?' for w in app.radio)
        assert not app.exception, str(app.exception)
        assert not any(w.label == 'Volume total (veículos/h)' for w in app.number_input)
        assert not any(w.label == 'Usar contagens reais para calibrar o tráfego' for w in app.toggle)
        assert not list(app.get('file_uploader'))
        assert not any('OD' in w.label for w in app.get('download_button'))
        import json
        layers = json.loads(app.get('deck_gl_json_chart')[0].proto.json)['layers']
        assert not any(w.label == 'Cruzamento para preencher os volumes' for w in app.selectbox)
        roads = next(l['data'] for l in layers if l['id'] == 'configuration-roads')
        assert len(roads) == 28
        road = next(r for r in roads if r['controllers'])
        entry = road['edge_id']
        search = next(w for w in app.selectbox if w.label == 'Buscar rua ou cruzamento no mapa')
        assert any(road['title'] in option for option in search.options)
        search.select(('roads', entry)).run()
        assert not any(w.label in ('Voltar à visão geral do mapa', 'Fechar ajustes') for w in app.button)
        namespace = next(k.rsplit('_chart_', 1)[0] for k in app.session_state.filtered_state if '_chart_' in k)
        apply_map_selection(app.session_state, namespace, {'roads': roads, 'signals': [], 'pedestrians': []},
                            {'selection': {'objects': {'configuration-roads': [road]}}})
        app.run()
        assert any(w.label == 'Incluir pedestres?' for w in app.toggle)
        next(w for w in app.number_input if w.label == 'Veículos por hora').set_value(600.).run()
        assert any('100 veículos previstos em 10 min' in w.value for w in app.markdown)
        assert not any(w.label == 'Ver uma prévia de 30 segundos' for w in app.button)
        assert any(w.label == 'Simular com os tempos iniciais' for w in app.button)
        launch.assert_not_called()
        next(w for w in app.button if w.label == 'Continuar: preparar o treinamento').click().run()
        assert app.session_state['ui_default_tab'] == '2 · Treinamento'
        assert next(w for w in app.number_input if w.label == 'Quantidade de decisões para treinar').value == 2048
        next(w for w in app.number_input if w.label == 'Quantidade de decisões para treinar').set_value(4096).run()
        assert not app.exception, str(app.exception)
        next(w for w in app.checkbox if w.label == 'Personalizar pesos do objetivo').check().run()
        next(w for w in app.number_input if w.label == 'Prioridade: filas').set_value(2.).run()
        next(w for w in app.button if w.label == 'Iniciar treinamento').click().run()
        launch.assert_called_once()
        config, command = launch.call_args.args[:2]
        assert command == 'rl-train'
        assert config['demand']['mode'] == 'edge_volumes'
        assert next(r['vehicles_per_hour'] for r in config['demand']['edge_volumes'] if r['from_edge'] == entry) == 600.
        assert config['experimental']['method'] == 'compatible_groups_v2'
        assert len(config['targets']) == 17
        assert config['ppo']['total_timesteps'] == 4096
        assert config['measurement']['end_seconds'] == config['duration_seconds']
        assert config['control']['action_mode'] == 'adaptive_signals'
        assert config['objectives']['queues'] == 2
        assert config['demand']['synthetic'] is True
        assert app.session_state['ui_default_tab'] == '3 · Resultados'
        assert not app.exception, str(app.exception)
print('AppTest aprovado: busca no mapa, estimativa, validacao e treino com executor substituido.')
