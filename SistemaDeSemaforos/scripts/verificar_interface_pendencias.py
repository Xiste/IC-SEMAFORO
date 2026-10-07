"""Verifica os formulários usados para operar os nove cruzamentos."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
next(w for w in app.radio if w.label == 'Cruzamentos controlados').set_value('Nove cruzamentos: cenário experimental').run()
next(w for w in app.button if w.label == 'Preparar e verificar os nove cruzamentos').click().run()
assert not app.exception, str(app.exception)
assert not app.error, str(app.error)
config = app.session_state['experimental_config']
assert config['experimental']['method'] == 'compatible_groups_v2'
assert len(config['targets']) == 17
next(w for w in app.radio if w.label == 'Modelo').set_value('Volume por via').run()
assert not app.exception, str(app.exception)
assert not app.error, str(app.error)
next(w for w in app.radio if w.label == 'O que estes volumes representam?').set_value('Contagens observadas: calibrar entradas da rede').run()
assert not app.exception, str(app.exception)
next(w for w in app.radio if w.label == 'Modelo').set_value('Pares origem–destino').run()
assert not app.exception, str(app.exception)
assert not any('Fluxos JSON' in w.label for w in app.text_area)
assert any(w.label == 'Executar simulação sem treinamento' for w in app.button)
print('Interface conjunta: 17 alvos, grupos v2, contagens calibradas, tabela OD e simulação sem treino verificados.')
