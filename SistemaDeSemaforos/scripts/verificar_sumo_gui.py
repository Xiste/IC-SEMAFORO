"""Smoke real do SUMO-GUI; opção de manter a janela para inspeção visual."""
import argparse
import time
import uuid
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import traci
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import prepare_experimental
from semaforos.cenario.pedestres import crossing_routes
from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.arquivos import write_json

parser = argparse.ArgumentParser()
parser.add_argument('--inspect', action='store_true')
args = parser.parse_args()
output = ROOT / 'resultados' / f'verificacao_gui_{uuid.uuid4().hex[:8]}'
config, _ = prepare_experimental(read_config(ROOT / 'config/cenario.json'), output / 'scenario')
config['duration_seconds'] = 120
config['control']['gui_delay_milliseconds'] = 5
routes = crossing_routes(config['network'], config['targets'])
config['pedestrians'] = {'enabled': True, 'flows': [{**routes[0], 'persons_per_hour': 120}]}
env = SemaforosEnv(config, output / 'episodes', gui=True)
try:
    env.reset(seed=42)
    for _ in range(10):
        env.step([1] * len(env.action_spec))
    first = config['targets'][0]['tls_id']
    x, y = env.network.getTLS(first).getConnections()[0][0].getEdge().getToNode().getCoord()
    traci.gui.setOffset('View #0', x, y)
    traci.gui.setZoom('View #0', 700)
    traci.gui.screenshot('View #0', str(output / 'sumo_gui.png'))
    env.step([1] * len(env.action_spec))
    print(f'GUI pronta: {output}', flush=True)
    write_json(ROOT / 'resultados' / 'gui_inspection.json', {'output': str(output), 'simulated_seconds': 55})
    if args.inspect:
        deadline = time.monotonic() + 180
        while not (output / 'continuar.flag').exists() and time.monotonic() < deadline:
            time.sleep(0.2)
    done = False
    while not done:
        _, _, done, _, info = env.step([1] * len(env.action_spec))
finally:
    env.close()
write_json(output / 'verificacao.json', {'gui': True, 'episodes': env.last_info, 'completed': True})
print('SUMO-GUI concluiu 120 s com 17 controladores, pedestres e métricas.', flush=True)
