import pytest

from semaforos.apresentacao.sinais import signal_movement_timings


def test_signal_timings_include_all_red_and_keep_different_turns_separate(tmp_path):
    network = tmp_path / 'network.xml'
    network.write_text('''<net>
      <edge id="a"/><edge id="b"/>
      <tlLogic id="tls">
        <phase duration="20" state="Grr"/><phase duration="3" state="yrr"/>
        <phase duration="2" state="rrr"/><phase duration="30" state="rGG"/>
        <phase duration="4" state="ryy"/><phase duration="1" state="rrr"/>
      </tlLogic>
      <connection tl="tls" linkIndex="0" from="a" to="b" dir="s"/>
      <connection tl="tls" linkIndex="0" from="a" to="b" dir="r"/>
      <connection tl="tls" linkIndex="1" from="a" to="b" dir="l"/>
      <connection tl="tls" linkIndex="2" from="b" to="a" dir="s"/>
    </net>''', encoding='utf-8')
    rows = signal_movement_timings(network, 'tls', {
        'a': {'reference':'Entrada 1','street':'Rua A','approach':'Segue para norte'},
        'b': {'reference':'Entrada 2','street':'Rua B','approach':'Segue para sul'}})
    assert len(rows) == 3
    a = [r for r in rows if r['Via'] == 'Rua A']
    assert len(a) == 2
    straight = next(r for r in a if 'Em frente' in r['Movimento'])
    assert 'À direita' in straight['Movimento']
    assert [straight[k] for k in ('Verde (s)','Amarelo (s)','Vermelho (s)')] == [20,3,37]
    left = next(r for r in a if r['Movimento'] == 'À esquerda')
    assert [left[k] for k in ('Verde (s)','Amarelo (s)','Vermelho (s)')] == [30,4,26]
    for row in rows:
        assert sum(row[k] for k in ('Verde (s)','Amarelo (s)','Vermelho (s)','Outros (s)')) == pytest.approx(row['Ciclo (s)'])


def test_pedestrian_signal_is_identified_as_crossing(tmp_path):
    network = tmp_path / 'network.xml'
    network.write_text('''<net><edge id="walk" function="walkingarea"/>
      <edge id="cross" function="crossing"/>
      <tlLogic id="ped"><phase duration="10" state="G"/><phase duration="2" state="y"/>
      <phase duration="20" state="r"/></tlLogic>
      <connection tl="ped" linkIndex="0" from="walk" to="cross" dir="s"/>
      </net>''', encoding='utf-8')
    row = signal_movement_timings(network, 'ped', {'cross': {'reference':'Travessia 1'}})[0]
    assert row['Entrada'] == 'Travessia 1'
    assert row['Via'] == 'Travessia de pedestres'
    assert row['Movimento'] == 'Atravessar'
    assert row['Verde (s)'] == 10
