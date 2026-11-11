"""Verifica os formulários usados para operar os nove cruzamentos."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

app = AppTest.from_file(str(ROOT / 'interface.py'), default_timeout=90).run()
next(w for w in app.radio if w.label == 'Cruzamentos controlados').set_value('Todos os nove').run()
next(w for w in app.button if w.label == 'Preparar simulação').click().run()
assert not app.exception, str(app.exception)
assert not app.error, str(app.error)
config = app.session_state['experimental_config']
assert config['experimental']['method'] == 'compatible_groups_v2'
assert len(config['targets']) == 17
next(w for w in app.radio if w.label == 'Cruzamentos controlados').set_value('Um cruzamento').run()
from semaforos.cenario.experimental import intersection_names
for name in intersection_names():
    next(w for w in app.selectbox if w.label == 'Qual cruzamento?').set_value(name).run()
    assert not app.exception, str(app.exception)
    assert not app.error, str(app.error)
    assert any('1 cruzamento(s)' in w.value for w in app.caption)
next(w for w in app.radio if w.label == 'Cruzamentos controlados').set_value('Todos os nove').run()
assert any('9 cruzamento(s)' in w.value for w in app.caption)
next(w for w in app.radio if w.label == 'Como deseja informar o tráfego?').set_value('Volume por via').run()
assert not app.exception, str(app.exception)
assert all('volume' in w.value.casefold() or 'entrada' in w.value.casefold() for w in app.error), str(app.error)
assert not list(app.get('file_uploader'))
assert len(next(w for w in app.radio if w.label == 'Como deseja informar o tr\u00e1fego?').options) == 2
assert not any('OD' in w.label for w in app.get('download_button'))
assert any(w.label == 'Simular com os tempos iniciais' for w in app.button)
print('Interface conjunta: selecao de cruzamentos, contagens e destinos automaticos verificados.')
