"""Seleção dos objetos e conservação dos ajustes ao navegar pelo mapa."""
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from semaforos.apresentacao.mapa_configuracao import (
    configuration_geometry, configuration_deck, apply_map_selection, map_selection,
)
from semaforos.apresentacao.vias import identify_roads
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.pedestres import crossing_routes
import sumolib
import pytest


def test_centerline_between_vehicle_lanes_with_different_vertices():
    from semaforos.apresentacao.mapa_configuracao import road_centerline
    center = road_centerline([[(0,0),(100,0)], [(0,4),(40,4),(100,4)]])
    assert center[0] == pytest.approx([0,2])
    assert center[-1] == pytest.approx([100,2])
    assert all(p[1] == pytest.approx(2) for p in center)


@pytest.mark.parametrize('shape, center, forward', [
    ([(0,0),(100,0)], (50,0), (1,0)),
    ([(0,100),(0,0)], (0,50), (0,-1)),
    ([(0,0),(20,0),(20,80)], (20,30), (0,1)),
    ([(0,0),(0,0),(40,40),(40,40)], (20,20), (1,1)),
])
def test_direction_arrow_center_and_orientation_follow_the_road(shape, center, forward):
    from semaforos.apresentacao.mapa_configuracao import road_direction_polygon
    # Escalas diferentes nos eixos expõem distorções causadas por rotação em graus.
    project = lambda p: [p[0] * .00001 - 48, p[1] * .00002 - 19]
    polygon = road_direction_polygon(shape, project)
    xy = [((p[0]+48)/.00001, (p[1]+19)/.00002) for p in polygon]
    centroid = [sum(p[i] for p in xy)/3 for i in (0,1)]
    assert centroid == pytest.approx(center, abs=1e-7)
    direction = [xy[0][i] - (xy[1][i]+xy[2][i])/2 for i in (0,1)]
    assert direction[0]*forward[1] - direction[1]*forward[0] == pytest.approx(0, abs=1e-7)
    assert sum(direction[i]*forward[i] for i in (0,1)) > 0
    assert sum(d*d for d in direction)**.5 <= 5.000001


def test_real_map_has_signal_icons_roads_and_pedestrian_lines(tmp_path):
    config = read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json')
    network = str(config['network'])
    targets = tuple((t['tls_id'], t['name']) for t in config['targets'])
    names = json.loads((PROJECT_ROOT / 'dados/auditoria/nomes_vias_osm.json').read_text(encoding='utf-8'))['ways']
    details = identify_roads(sumolib.net.readNet(network), targets, names)
    geometry = configuration_geometry(network, Path(network).stat().st_mtime_ns, targets, details,
                                      crossing_routes(network, config['targets']))
    assert {r['tls_id'] for r in geometry['signals']} == {t[0] for t in targets}
    assert geometry['roads'] and geometry['pedestrians']
    assert all(-180 < r['position'][0] < 180 and -90 < r['position'][1] < 90 for r in geometry['signals'])
    deck = json.loads(configuration_deck(geometry, targets[0][1], {}).to_json())
    layers = {r['id']: r for r in deck['layers']}
    assert layers['configuration-signals']['@@type'] == 'GeoJsonLayer'
    assert layers['configuration-signals']['pointType'] == 'icon'
    assert layers['configuration-signals']['_subLayerProps']['polygons-fill']['pickable'] is False
    assert layers['configuration-signals']['getFillColor'][-1] == 1
    ids = [layer['id'] for layer in deck['layers']]
    assert ids.index('configuration-roads') < ids.index('configuration-signals') < ids.index('configuration-directions')
    for feature in layers['configuration-signals']['data']:
        expected_edges = {r['edge_id'] for r in geometry['roads'] if feature['tls_id'] in r['controllers']}
        assert set(feature['affected_edges']) == expected_edges
        assert feature['geometry']['geometries'][0]['type'] == 'Point'
        assert feature['geometry']['geometries'][1]['type'] == 'MultiPolygon'
        assert feature['geometry']['geometries'][1]['coordinates']
    assert layers['configuration-signals']['pickable']
    assert layers['configuration-roads']['pickable']
    assert layers['configuration-pedestrians']['@@type'] == 'PathLayer'
    assert layers['configuration-directions']['data']
    # Rua Parana tem quatro faixas: desenhar apenas a primeira desloca a seta.
    parana = next(r for r in geometry['roads'] if r['edge_id'] == '1156717168')
    import xml.etree.ElementTree as ET
    element = next(e for e in ET.parse(network).getroot().findall('edge') if e.get('id') == '1156717168')
    starts = [list(map(float, lane.get('shape').split()[0].split(','))) for lane in element.findall('lane')]
    expected = [sum(p[i] for p in starts)/len(starts) for i in (0,1)]
    assert parana['xy'][0] == pytest.approx(expected)
    assert parana['xy'][0] != starts[0]
    other = next(edge.getID() for edge in sumolib.net.readNet(network).getEdges()
                 if edge.allows('passenger') and edge.getOutgoing()
                 and edge.getID() not in {r['edge_id'] for r in geometry['roads']})
    editable = tuple([r['edge_id'] for r in geometry['roads']] + [other])
    all_geometry = configuration_geometry(network, Path(network).stat().st_mtime_ns, targets, details, [], editable)
    assert other in {r['edge_id'] for r in all_geometry['roads']}
    before = json.loads(configuration_deck(all_geometry, None, {}).to_json())
    after = json.loads(configuration_deck(all_geometry, 'Outro local', {'kind':'road','edge_id':other}).to_json())
    assert before['initialViewState'] == after['initialViewState']
    assert len(next(l for l in after['layers'] if l['id']=='configuration-roads')['data']) == len(editable)
    from semaforos.cenario.demanda import create_edge_volume_demand
    import xml.etree.ElementTree as ET
    demand_config = {**config, 'duration_seconds':30,
                     'demand': {'mode':'edge_volumes','edge_volumes':[{'from_edge':other,'vehicles_per_hour':120.}]}}
    trips = create_edge_volume_demand(demand_config, sumolib.net.readNet(network), tmp_path, 11)
    generated = ET.parse(trips).getroot().findall('trip')
    assert len(generated) == 1 and generated[0].get('from') == other


def test_map_selection_accepts_only_real_objects_and_switches_panel():
    geometry = {'signals': [{'kind':'signal','tls_id':'a','crossing':'Local A'}],
                'roads': [{'kind':'road','edge_id':'in','crossing':'Local A'}],
                'pedestrians': [{'kind':'pedestrian','crossing_id':'cross','crossing':'Local B'}]}
    state = {}
    for layer, field, value, expected in [('configuration-signals','tls_id','a','Semáforos'),
                                         ('configuration-roads','edge_id','in','Veículos'),
                                         ('configuration-pedestrians','crossing_id','cross','Pedestres')]:
        apply_map_selection(state, 'map', geometry,
                            {'selection': {'objects': {layer: [{field:value, 'crossing':'Nome incorreto'}]}}},
                            demand_mode_key='demand')
        assert state['map_mode'] == expected
        assert state['map_selected']['crossing'] in ('Local A','Local B')
    assert state['map_crossing'] == 'Local B'
    assert state['demand'] == 'Volume por via'
    assert map_selection({'selection': {'objects': {'configuration-signals': [{'tls_id':'unknown'}]}}}, geometry) is None
    assert map_selection({'selection': {'objects': {}}}, geometry) is None


def test_map_panels_preserve_road_and_green_edits_between_crossings(tmp_path):
    network = tmp_path / 'network.xml'
    network.write_text('''<net><location netOffset="0,0" projParameter="+proj=utm +zone=23 +south +datum=WGS84"/>
      <edge id="a"><lane id="a_0" shape="500000,7900000 500000,7900010"/></edge>
      <edge id="b"><lane id="b_0" shape="500100,7900000 500100,7900010"/></edge>
      <connection tl="a" from="a" to="out" linkIndex="0" dir="s"/>
      <connection tl="b" from="b" to="out" linkIndex="0" dir="s"/>
      <tlLogic id="a"><phase state="G" duration="20"/><phase state="y" duration="3"/><phase state="r" duration="2"/></tlLogic>
      <tlLogic id="b"><phase state="G" duration="20"/><phase state="y" duration="3"/><phase state="r" duration="2"/></tlLogic>
      </net>''', encoding='utf-8')
    source = f'''
import streamlit as st
from semaforos.apresentacao.mapa_configuracao import render_configuration_map
base = {{'network':{str(network)!r}, 'targets':[{{'tls_id':'a','name':'Local A'}},{{'tls_id':'b','name':'Local B'}}]}}
initial = [dict(from_edge=e, vehicles_per_hour=10., to_edge='') for e in ('a','b')]
details = {{e: dict(crossing='Local '+e.upper(), reference='Entrada '+e, street='Rua '+e, approach='norte', label=e) for e in ('a','b')}}
specs = [dict(tls_id=tls,phase_index=i,kind=kind,durations_seconds=bounds) for tls in ('a','b')
         for i,kind,bounds in [(0,'green',[10,20,30]),(1,'yellow',[3,3,3]),(2,'all_red',[2,2,2])]]
from semaforos.apresentacao.mapa_configuracao import apply_map_selection
from semaforos.apresentacao.estado import configuration_key
namespace = configuration_key('configuration_map_' + str(base['network']))
g = {{'signals':[dict(kind='signal',tls_id=e,crossing='Local '+e.upper()) for e in ('a','b')],
      'roads':[dict(kind='road',edge_id=e,crossing='Local '+e.upper()) for e in ('a','b')], 'pedestrians':[]}}
def pick(layer, field, value):
    apply_map_selection(st.session_state,namespace,g,{{'selection':{{'objects':{{layer:[{{field:value}}]}}}}}})
st.button('Via A', on_click=pick, args=('configuration-roads','edge_id','a'))
st.button('Via B', on_click=pick, args=('configuration-roads','edge_id','b'))
st.button('Sinal A', on_click=pick, args=('configuration-signals','tls_id','a'))
roads, pedestrians, limits, enabled, speed = render_configuration_map(base,initial,details,('a','b'),specs,{{'a':'Rua A','b':'Rua B'}},[],volume_by_road=True)
st.session_state.roads = roads.to_dict('records')
st.session_state.limits = limits.to_dict('records')
'''
    app = AppTest.from_string(source).run()
    assert not app.exception
    def edit(token, changes):
        key = next(k for k,v in app.session_state.filtered_state.items() if token in k and isinstance(v,dict) and 'edited_rows' in v)
        app.session_state[key] = {'edited_rows': {0:changes},'added_rows':[],'deleted_rows':[]}
        app.run()
        assert not app.exception
    assert not any(w.label == 'Cruzamento no mapa' for w in app.selectbox)
    assert not any(w.label == 'Veículos por hora' for w in app.number_input)
    app.button[0].click().run()
    next(w for w in app.number_input if w.label == 'Veículos por hora').set_value(420.).run()
    app.button[2].click().run()
    next(w for w in app.number_input if w.label == 'Verde mínimo (s)').set_value(12.).run()
    next(w for w in app.number_input if w.label == 'Verde máximo (s)').set_value(35.).run()
    assert not any('entries' in item.value.columns for item in app.dataframe)
    app.button[1].click().run()
    next(w for w in app.number_input if w.label == 'Veículos por hora').set_value(160.).run()
    next(w for w in app.button if w.label == 'Fechar ajustes').click().run()
    app.button[0].click().run()
    assert not app.exception
    assert next(w for w in app.number_input if w.label == 'Veículos por hora').value == 420.
    assert [r['vehicles_per_hour'] for r in app.session_state.roads] == [420.,160.]
    assert app.session_state.limits[0]['minimum_seconds'] == 12.
    assert app.session_state.limits[0]['maximum_seconds'] == 35.
    assert app.session_state.limits[3]['minimum_seconds'] == 10.
