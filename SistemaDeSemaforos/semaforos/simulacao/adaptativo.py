"""Observações de sensores virtuais e escolha adaptativa de aberturas compatíveis."""
import traci


def sensor_layout(network, targets):
    """Contrato estável por faixa, com entradas e saídas explicitamente associadas."""
    rows = []
    for target in targets:
        light = network.getTLS(target['tls_id'])
        grouped = {}
        for incoming, outgoing, link in light.getConnections():
            item = grouped.setdefault(incoming.getID(), {'outgoing': set(), 'links': set(),
                'edge_id': incoming.getEdge().getID(),
                'pedestrian': incoming.getEdge().getFunction() in ('walkingarea', 'crossing')})
            item['outgoing'].add(outgoing.getID())
            item['links'].add(link)
        for lane, item in sorted(grouped.items()):
            rows.append({'tls_id': target['tls_id'], 'lane_id': lane,
                         'edge_id': item['edge_id'], 'pedestrian': item['pedestrian'],
                         'outgoing': sorted(item['outgoing']), 'links': sorted(item['links'])})
    return rows


def sensor_values(layout):
    """SUMO representa presença, contagem, fila, velocidade e ocupação dos sensores."""
    values = []
    for item in layout:
        lane = item['lane_id']
        count = traci.lane.getLastStepVehicleNumber(lane)
        capacity = max(1., traci.lane.getLength(lane) / 7.5)
        outgoing = item['outgoing']
        if item.get('pedestrian'):
            people = traci.edge.getLastStepPersonIDs(item['edge_id'])
            count = len(people)
            halted = sum(traci.person.getWaitingTime(p) > 0 for p in people)
            speed = sum(traci.person.getSpeed(p) for p in people) / max(1, count)
            values.extend((float(count > 0), min(1., count / capacity), min(1., halted / capacity),
                           min(1., max(0., speed) / 3), min(1., count / capacity), 0.))
            continue
        values.extend((float(count > 0),
                       min(1., count / capacity),
                       min(1., traci.lane.getLastStepHaltingNumber(lane) / capacity),
                       max(0., min(1., traci.lane.getLastStepMeanSpeed(lane) / max(.1, traci.lane.getMaxSpeed(lane)))),
                       max(0., min(1., traci.lane.getLastStepOccupancy(lane) / 100)),
                       max([max(0., min(1., traci.lane.getLastStepOccupancy(out) / 100)) for out in outgoing] or [0.])))
    return values


class AdaptiveSignals:
    """Seleciona verdes sem impor ordem cíclica; executa amarelo e limpeza completos.

    A rede precisa conter trios verde/amarelo/todos vermelhos. Nenhum estado
    semafórico novo é inventado; apenas verdes já cadastrados podem ser escolhidos.
    """
    def __init__(self, specs, programs, step, service_trigger=120):
        self.specs, self.programs, self.step = specs, programs, step
        self.requests = {}
        self.pending = {}
        self.last_served = {}
        self.service_trigger = service_trigger

    def request(self, action):
        self.requests = {s['tls_id']: s['green_indices'][int(a)] for s, a in zip(self.specs, action)}

    def tick(self, now):
        events = []
        for spec in self.specs:
            tls = spec['tls_id']
            if tls not in self.requests:
                continue
            phases = self.programs[tls]
            current = traci.trafficlight.getPhase(tls)
            elapsed = traci.trafficlight.getSpentDuration(tls)
            desired = self.requests[tls]
            served = self.last_served.setdefault(tls, {i: now for i in spec['green_indices']})
            next_index = None
            if current in spec['green_indices']:
                served[current] = now
                low, high = spec['green_bounds'][str(current)]
                oldest = min(served, key=served.get)
                if now - served[oldest] >= self.service_trigger:
                    desired = oldest
                # Nunca deixa o SUMO avançar sozinho antes da decisão protegida.
                if elapsed >= high and len(spec['green_indices']) > 1:
                    if desired == current:
                        desired = min((i for i in served if i != current), key=served.get)
                if (desired != current or elapsed >= high) and elapsed >= low:
                    self.pending[tls] = desired
                    next_index = current + 1
            elif elapsed >= phases[current]['duration']:
                if all(c in 'rR' for c in phases[current]['state']):
                    next_index = self.pending.pop(tls, desired)
                else:
                    next_index = (current + 1) % len(phases)
            if next_index is not None:
                traci.trafficlight.setPhase(tls, next_index)
                events.append({'time_seconds': now, 'tls_id': tls, 'phase_index': next_index,
                               'requested_green': desired, 'previous_phase': current,
                               'previous_elapsed_seconds': elapsed})
            # Reavaliado a cada passo, inclusive entre decisões do PPO.
            traci.trafficlight.setPhaseDuration(tls, max(2 * self.step, self.step + 1))
        return events


def adaptive_specs(config, programs, duration_specs):
    result = []
    for target in config['targets']:
        tls, greens = target['tls_id'], target['phase_indices']
        phases = programs[tls]
        if len(phases) != 3 * len(greens) or greens != list(range(0, len(phases), 3)):
            raise ValueError('Controle adaptativo requer rede preparada com verdes, amarelos e limpeza separados')
        for index in greens:
            green, yellow, red = (phases[index + i]['state'] for i in range(3))
            if (not any(c in 'Gg' for c in green) or not all(c in 'rR' for c in red)
                    or len(green) != len(yellow) or len(green) != len(red)
                    or any((g in 'Gg' and y not in 'yY') or (g not in 'Gg' and y not in 'rR')
                           for g, y in zip(green, yellow))):
                raise ValueError(f'Transição adaptativa incompatível em {tls}:{index}')
        bounds = {str(s['phase_index']): [s['durations_seconds'][0], s['durations_seconds'][2]]
                  for s in duration_specs if s['tls_id'] == tls and s['kind'] == 'green'}
        if set(bounds) != {str(i) for i in greens}:
            raise ValueError('Todos os verdes precisam de limites no controle adaptativo')
        result.append({'tls_id': tls, 'green_indices': greens, 'green_bounds': bounds})
    return result
