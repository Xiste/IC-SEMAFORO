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
        labels = [t.label for t in app.get('tab')]
        assert labels[:5] == ['1 · Cenário', '2 · Tráfego', '3 · Treinamento', '4 · Resultados', 'Referência técnica'], labels
        assert any(w.label == 'Ajustes avançados do treinamento' for w in app.get('expander'))
        assert any(w.label == 'Cruzamentos no estudo' and str(w.value) == '1' for w in app.metric)
        assert next(w for w in app.button if w.label == 'Avaliar PPO e referência').disabled
        launch.assert_not_called()
        next(w for w in app.button if w.label == 'Continuar: configurar o tráfego').click().run()
        assert app.session_state['ui_default_tab'] == '2 · Tráfego'
        next(w for w in app.number_input if w.label == 'Aquecimento sem atuação do algoritmo (s)').set_value(600.0).run()
        assert next(w for w in app.button if w.label == 'Iniciar treinamento PPO').disabled
        assert any('configuração precisa' in w.value for w in app.error)
        next(w for w in app.number_input if w.label == 'Aquecimento sem atuação do algoritmo (s)').set_value(60.0).run()
        next(w for w in app.number_input if w.label == 'Total de passos de treinamento').set_value(4096).run()
        assert not app.exception, str(app.exception)
        assert any(w.label == 'Tempo de medição' and w.value == '540 s' for w in app.metric)
        assert any(w.label == 'Passos de treinamento' and w.value == '4.096' for w in app.metric)
        next(w for w in app.button if w.label == 'Iniciar treinamento PPO').click().run()
        launch.assert_called_once()
        config, command = launch.call_args.args[:2]
        assert command == 'rl-train'
        assert config['ppo']['total_timesteps'] == 4096
        assert config['measurement']['warmup_seconds'] == 60
        assert app.session_state['ui_default_tab'] == '4 · Resultados'
        assert not app.exception, str(app.exception)
print('AppTest aprovado: cinco abas, resumo atualizado, validação, avaliação bloqueada sem modelo e treinamento com início substituído.')
