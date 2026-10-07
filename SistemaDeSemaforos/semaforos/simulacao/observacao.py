"""Medições por cruzamento com união de faixas, sem alterar o controlador."""
import csv
import time
from pathlib import Path

import traci

from semaforos.arquivos import write_json


class IntersectionMetrics:
    def __init__(self, targets, controlled_lanes, step):
        self.step = step
        self.lanes = {}
        self.controllers = {}
        for target in targets:
            name = target['name']
            self.lanes.setdefault(name, set()).update(controlled_lanes[target['tls_id']])
            self.controllers.setdefault(name, []).append(target['tls_id'])
        self.values = {name: {'queue_vehicle_seconds': 0.0, 'peak_halted_vehicles': 0,
                             'speed_sum': 0.0, 'occupancy_sum': 0.0, 'lane_samples': 0,
                             'wait_vehicle_seconds': 0.0} for name in self.lanes}
        self.previous_wait = {}
        self.halted = {}

    def sample(self, details=True):
        for name, lanes in self.lanes.items():
            values = self.values[name]
            halted = sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
            self.halted[name] = halted
            values['queue_vehicle_seconds'] += halted * self.step
            values['peak_halted_vehicles'] = max(values['peak_halted_vehicles'], halted)
            vehicles = {vehicle for lane in lanes for vehicle in traci.lane.getLastStepVehicleIDs(lane)}
            current = {v: traci.vehicle.getWaitingTime(v) for v in vehicles}
            # Incrementos por veículo; sua espera anterior a chegar não pertence ao cruzamento.
            for vehicle, waiting in current.items():
                previous = self.previous_wait.get((name, vehicle))
                values['wait_vehicle_seconds'] += min(self.step, waiting) if previous is None else max(0, waiting - previous)
            for key in [key for key in self.previous_wait if key[0] == name]:
                del self.previous_wait[key]
            self.previous_wait.update({(name, v): value for v, value in current.items()})
            if details:
                for lane in lanes:
                    speed = traci.lane.getLastStepMeanSpeed(lane)
                    if speed >= 0:
                        values['speed_sum'] += speed
                        values['occupancy_sum'] += traci.lane.getLastStepOccupancy(lane)
                        values['lane_samples'] += 1

    def rows(self):
        return [{'intersection': name, 'controller_count': len(self.controllers[name]),
                 'unique_lane_count': len(self.lanes[name]),
                 **{k: v for k, v in values.items() if k not in ('speed_sum', 'occupancy_sum', 'lane_samples')},
                 'mean_lane_speed_meters_per_second': values['speed_sum'] / values['lane_samples'] if values['lane_samples'] else None,
                 'mean_lane_occupancy_percent': values['occupancy_sum'] / values['lane_samples'] if values['lane_samples'] else None}
                for name, values in self.values.items()]


class LiveMetrics:
    """Arquivo pequeno para o painel e série CSV incremental por decisão."""
    def __init__(self, output, episode, seed, parent):
        self.output, self.parent = Path(output), Path(parent)
        self.episode, self.seed = episode, seed
        self.started = time.perf_counter()

    def record(self, info, reward, intersections, pedestrians):
        row = {'episode': self.episode, 'seed': self.seed,
               'simulated_seconds': info['simulated_seconds'], 'reward_step': reward,
               'queue_vehicles_now': sum(intersections.halted.values()),
               **{key: info[key] for key in ('departed', 'arrived', 'wait_vehicle_seconds', 'global_halted_vehicle_seconds')},
               **pedestrians, 'real_seconds': round(time.perf_counter() - self.started, 3)}
        path = self.output / 'live_history.csv'
        exists = path.exists()
        with path.open('a', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            if not exists:
                writer.writeheader()
            writer.writerow(row)
        write_json(self.parent / 'live.json', {**row, 'episode_output': str(self.output),
                                             'intersections': intersections.rows()})
