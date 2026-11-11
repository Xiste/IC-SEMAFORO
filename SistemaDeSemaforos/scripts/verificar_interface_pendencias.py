"""Verifica os formulários usados para operar os nove cruzamentos."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
assert not any(w.label == 'Cruzamentos controlados' for w in app.radio)
assert not any(w.label == 'Qual cruzamento?' for w in app.selectbox)
next(w for w in app.button if w.label == 'Preparar simulação').click().run()
assert not app.exception, str(app.exception)
assert all('volume' in w.value.casefold() or 'entrada' in w.value.casefold() for w in app.error), str(app.error)
config = app.session_state['experimental_config']
assert config['experimental']['method'] == 'compatible_groups_v2'
assert len(config['targets']) == 17
from semaforos.cenario.experimental import intersection_names
assert {t['name'] for t in config['targets']} == set(intersection_names())
assert any('9 cruzamento(s)' in w.value for w in app.caption)
assert not any(w.label == 'Como deseja informar o tráfego?' for w in app.radio)
assert not app.exception, str(app.exception)
assert all('volume' in w.value.casefold() or 'entrada' in w.value.casefold() for w in app.error), str(app.error)
assert not list(app.get('file_uploader'))
assert not any('OD' in w.label for w in app.get('download_button'))
assert any(w.label == 'Simular com os tempos iniciais' for w in app.button)
print('Interface conjunta: selecao de cruzamentos, contagens e destinos automaticos verificados.')
