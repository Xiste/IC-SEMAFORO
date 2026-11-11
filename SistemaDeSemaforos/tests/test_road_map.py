import json
import unittest
from pathlib import Path

import sumolib

from semaforos.caminhos import PROJECT_ROOT
from semaforos.apresentacao.mapa_vias import road_map_data, road_deck, short_path, arrow_polygon, junction_exits
from semaforos.apresentacao.vias import identify_roads


class RoadMapTest(unittest.TestCase):
    def test_clipping_keeps_direction(self):
        self.assertEqual(short_path([(0, 0), (100, 0), (100, 100)], 50), [[0, 0], [50, 0]])
        self.assertEqual(short_path([(0, 0), (100, 0), (100, 100)], 50, end=True), [[100, 50], [100, 100]])
        arrow = arrow_polygon([(0, 0), (100, 0)])
        self.assertGreater(arrow[0][0], arrow[1][0])

    def test_exit_links_and_geographical_coordinates_match_sumo(self):
        path = PROJECT_ROOT / 'dados/rede/uberlandia.rondon_norte_corrigida.net.xml'
        net = sumolib.net.readNet(str(path), withInternal=True)
        details = identify_roads(net, [('FAM_RONDON_PARANA', 'Rondon x Parana')])
        labels = {edge: row['label'] for edge, row in details.items()}
        incoming = [edge for edge, row in details.items() if row['reference'].startswith('Entrada ')]
        edge_id = max(incoming, key=lambda edge: len(net.getEdge(edge).getOutgoing()))
        data = road_map_data(str(path), path.stat().st_mtime_ns, edge_id, labels, tuple(incoming), 180)
        routes, nodes = junction_exits(net, net.getEdge(edge_id))
        self.assertTrue(routes)
        for roads, connections in routes:
            previous = net.getEdge(edge_id)
            for edge, connection in zip(roads, connections):
                self.assertIn(edge, previous.getOutgoing())
                self.assertIn(connection, previous.getOutgoing()[edge])
                previous = edge
            self.assertNotIn(roads[-1].getToNode().getID(), nodes)
        self.assertEqual({r['edge_id'] for r in data['paths'] if r['kind'] == 'exit'}, {roads[-1].getID() for roads, _ in routes})
        self.assertTrue(data['center_geo'])
        self.assertAlmostEqual(data['center_geo'][0], -48.25, delta=.05)
        self.assertAlmostEqual(data['center_geo'][1], -18.9, delta=.05)
        self.assertTrue(all(len(row['polygon']) == 3 for row in data['paths']))
        deck = json.loads(road_deck(data, show_others=False).to_json())
        self.assertEqual(len(deck['layers']), 5)
        self.assertEqual(deck['layers'][0]['widthUnits'], 'pixels')
        self.assertEqual(deck['layers'][-1]['characterSet'], 'auto')
        paths = deck['layers'][1]['data']
        self.assertFalse(any(row['kind'] == 'other' for row in paths))
