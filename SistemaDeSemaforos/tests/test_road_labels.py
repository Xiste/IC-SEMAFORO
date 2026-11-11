import unittest
from types import SimpleNamespace

from semaforos.apresentacao.vias import identify_roads


class RoadLabelTest(unittest.TestCase):
    def test_unnamed_curved_entrances_have_unique_references_and_arrival_direction(self):
        class Edge:
            def __init__(self, edge_id, shape, name=''):
                self.edge_id, self.shape, self.name = edge_id, shape, name

            def getID(self): return self.edge_id
            def getShape(self): return self.shape
            def getName(self): return self.name
            def allows(self, vehicle): return True

        edges = [Edge('123#0', [(0, 0), (100, 0), (100, 20)]),
                 Edge('second', [(0, 0), (0, 20)], ':synthetic'),
                 Edge('456#0', [(30, 0), (0, 0)])]
        light = SimpleNamespace(getID=lambda: 'signal',
            getConnections=lambda: [(SimpleNamespace(getEdge=lambda edge=edge: edge),) for edge in edges])
        network = SimpleNamespace(getTrafficLights=lambda: [light], getEdges=lambda **kwargs: edges)
        details = identify_roads(network, [('signal', 'Avenida A x Rua B')], {'456': {'name': 'Rua B'}})
        self.assertEqual(len({row['label'] for row in details.values()}), 3)
        self.assertEqual(details['second']['street'], '')
        self.assertEqual(details['456#0']['street'], 'Rua B')
        self.assertIn('chega pelo sul, segue para norte', details['123#0']['label'])
        for row in details.values():
            self.assertIn('Entrada ', row['label'])
            self.assertIn('Avenida A x Rua B', row['label'])
            self.assertNotIn('Via sem nome cadastrado', row['label'])
            self.assertNotIn('[', row['label'])
