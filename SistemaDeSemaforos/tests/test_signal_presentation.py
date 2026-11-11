import tempfile
from pathlib import Path

from semaforos.apresentacao.sinais import signal_presentation, movement_figure


def test_readable_entries_and_map_follow_exact_green_connections():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'net.xml'
        path.write_text('''<net>
        <edge id="a"><lane id="a_0" index="0" shape="0,0 100,0"/></edge>
        <edge id="b"><lane id="b_0" index="0" shape="100,0 200,0"/></edge>
        <connection tl="signal" from="a" to="b" fromLane="0" toLane="0" dir="s" linkIndex="0"/>
        <connection tl="signal" from="b" to="a" fromLane="0" toLane="0" dir="l" linkIndex="1"/>
        <tlLogic id="signal"><phase duration="20" state="Gr"/><phase duration="3" state="yr"/>
        <phase duration="2" state="rr"/><phase duration="30" state="rG"/>
        <phase duration="3" state="ry"/><phase duration="2" state="rr"/></tlLogic></net>''', encoding='utf-8')
        config = {'network': path, 'targets': [{'name': 'Local', 'tls_id': 'signal', 'phase_indices': [0, 3]}]}
        rows = signal_presentation(config, {'a': 'Entrada 1 · Local · Rua A', 'b': 'Entrada 2 · Local · Rua B'})
        assert rows[0]['_controller_label'] == 'Semáforos — Entrada 1, Entrada 2'
        assert rows[0]['Movimentos liberados'] == 'Entrada 1 · Rua A: seguir em frente'
        assert 'virar à esquerda' in rows[1]['Movimentos liberados']
        assert [p['green'] for p in rows[0]['_paths']] == [True, False]
        assert [p['green'] for p in rows[1]['_paths']] == [False, True]
        assert rows[0]['Verde (s)'] == 20
        assert rows[0]['Vermelho total (s)'] == 37
        assert rows[0]['_paths'][0]['path'][0] == [35., 0.]
        assert movement_figure(rows[0]['_paths']).axes
