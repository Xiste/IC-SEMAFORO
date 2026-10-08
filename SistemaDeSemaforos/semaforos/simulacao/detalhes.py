"""Métricas físicas de faixas/movimentos e indicadores exploratórios de dinâmica."""
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np
import traci


def distribution(values, prefix):
    data = np.asarray(values, dtype=float)
    if not len(data):
        return {f'{stat}_{prefix}': None for stat in ('mean', 'p50', 'p90', 'p95', 'p99', 'max')}
    return {f'mean_{prefix}': float(data.mean()), f'max_{prefix}': float(data.max()),
            **{f'p{p}_{prefix}': float(np.percentile(data, p)) for p in (50, 90, 95, 99)}}


def metric_settings(config):
    values = {'halt_speed_meters_per_second': .1, 'spillback_occupancy_percent': 80,
              'downstream_occupancy_percent': 80, 'long_wait_seconds': 120,
              'hard_braking_meters_per_second_squared': 4, 'ttc_seconds': 1.5,
              **config.get('metrics', {}).get('thresholds', {})}
    if any(not math.isfinite(float(v)) or float(v) <= 0 for v in values.values()):
        raise ValueError('Limiares das métricas devem ser positivos e finitos')
    if any(float(values[k]) > 100 for k in ('spillback_occupancy_percent', 'downstream_occupancy_percent')):
        raise ValueError('Limiares de ocupação não podem superar 100%')
    return {k: float(v) for k, v in values.items()}


class DetailedMetrics:
    def __init__(self, config, output, network_root):
        self.settings = metric_settings(config)
        self.options = config.get('metrics', {})
        self.enabled = self.options.get('collect_extended', True)
        self.dynamics = self.enabled and self.options.get('collect_vehicle_dynamics', True)
        self.output = Path(output).resolve()
        self.file = None
        self.seconds = 0.0
        self.lanes, self.movements, self.detectors = {}, {}, {}
        self.previous_wait, self.previous_speed, self.previous_acceleration = {}, {}, {}
        self.global_values = defaultdict(float)
        self.lane_values, self.movement_values = {}, {}
        self.samples = defaultdict(list)
        self.passed = defaultdict(set)
        self.previous_presence = {}
        self.class_cache = {}
        self.class_values = defaultdict(lambda: defaultdict(float))
        self.class_vehicles = defaultdict(set)
        if not self.enabled:
            return
        names = {t['tls_id']: t['name'] for t in config['targets']}
        edge_info = {e.get('id'): e for e in network_root.findall('edge')}
        lane_info = {l.get('id'): l for e in edge_info.values() for l in e.findall('lane')}
        for c in network_root.findall('connection'):
            tls, origin, destination = c.get('tl'), c.get('from'), c.get('to')
            if tls not in names or edge_info[origin].get('function') in ('crossing', 'walkingarea') or edge_info[destination].get('function') in ('crossing', 'walkingarea'):
                continue
            lane, outgoing = f"{origin}_{c.get('fromLane')}", f"{destination}_{c.get('toLane')}"
            key = f"{tls}:{c.get('linkIndex')}"
            self.lanes.setdefault(lane, {'lane_id': lane, 'edge_id': origin, 'intersection': names[tls],
                                         'length_meters': float(lane_info[lane].get('length')), 'shape': lane_info[lane].get('shape', '')})
            move = self.movements.setdefault(key, {'movement_id': key, 'tls_id': tls, 'link_index': int(c.get('linkIndex')),
                'intersection': names[tls], 'incoming': set(), 'outgoing': set(), 'via': set(), 'direction': c.get('dir', '')})
            move['incoming'].add(lane)
            move['outgoing'].add(outgoing)
            if c.get('via') in lane_info:
                move['via'].add(c.get('via'))
        additional = ET.Element('additional')
        for i, (lane, geometry) in enumerate(sorted(self.lanes.items())):
            detector = f'extended_queue_{i}'
            self.detectors[lane] = detector
            ET.SubElement(additional, 'laneAreaDetector', id=detector, lane=lane, pos='0',
                          length=str(geometry['length_meters']), period=str(config['duration_seconds']),
                          speedThreshold=str(self.settings['halt_speed_meters_per_second']), timeThreshold='1', jamThreshold='10',
                          file=str(self.output / 'lanearea_output.xml'))
        via_owners = defaultdict(set)
        for key, movement in self.movements.items():
            for via in movement['via']:
                via_owners[via].add(key)
        self.movement_detectors = defaultdict(list)
        for key, movement in self.movements.items():
            available = bool(movement['via']) and all(len(via_owners[v]) == 1 for v in movement['via'])
            movement['movement_flow_available'] = available
            if available:
                for via in sorted(movement['via']):
                    detector = f'extended_flow_{len(self.movement_detectors[key])}_{key.replace(":", "_")}'
                    ET.SubElement(additional, 'inductionLoop', id=detector, lane=via,
                                  pos=str(float(lane_info[via].get('length')) / 2), period=str(config['duration_seconds']),
                                  file=str(self.output / 'movement_detector_output.xml'))
                    self.movement_detectors[key].append(detector)
        if len(additional):
            self.file = self.output / 'extended_detectors.add.xml'
            ET.ElementTree(additional).write(self.file, encoding='utf-8', xml_declaration=True)
        self.lane_values = {lane: defaultdict(float) for lane in self.lanes}
        self.movement_values = {key: defaultdict(float) for key in self.movements}

    def prime(self, speeds):
        self.previous_speed = dict(speeds)

    def sample(self, step, speeds, waits, window_start):
        if not self.enabled:
            return
        self.seconds += step
        threshold = self.settings
        self.global_values['vehicle_distance_meters'] += sum(speeds.values()) * step
        self.global_values['moving_vehicle_seconds'] += sum(v >= threshold['halt_speed_meters_per_second'] for v in speeds.values()) * step
        self.global_values['long_wait_vehicle_seconds'] += sum(v >= threshold['long_wait_seconds'] for v in waits.values()) * step
        self.global_values['maximum_vehicle_wait_seconds'] = max([self.global_values['maximum_vehicle_wait_seconds'], *waits.values()])
        halted_global = sum(speed < threshold['halt_speed_meters_per_second'] for speed in speeds.values())
        self.samples[('global', 'queue')].append(halted_global)
        self.global_values['all_vehicles_stopped_seconds'] += bool(speeds and halted_global == len(speeds)) * step
        lane_cache, next_movements = {}, {}
        for lane, geometry in self.lanes.items():
            values = self.lane_values[lane]
            vehicles = traci.lane.getLastStepVehicleIDs(lane)
            halted = sum(speeds.get(v, 0) < threshold['halt_speed_meters_per_second'] for v in vehicles)
            occupancy = traci.lane.getLastStepOccupancy(lane)
            jam = traci.lanearea.getJamLengthMeters(self.detectors[lane])
            jam_vehicles = traci.lanearea.getJamLengthVehicle(self.detectors[lane])
            values['queue_vehicle_seconds'] += halted * step
            values['active_vehicle_seconds'] += len(vehicles) * step
            values['vehicle_distance_meters'] += sum(speeds.get(v, 0) for v in vehicles) * step
            values['occupancy_percent_seconds'] += occupancy * step
            values['peak_halted_vehicles'] = max(values['peak_halted_vehicles'], halted)
            values['maximum_jam_length_meters'] = max(values['maximum_jam_length_meters'], jam)
            values['maximum_jam_vehicles'] = max(values['maximum_jam_vehicles'], jam_vehicles)
            spill = occupancy >= threshold['spillback_occupancy_percent'] or jam >= .9 * geometry['length_meters']
            values['spillback_seconds'] += bool(spill) * step
            self.samples[('lane', lane, 'jam')].append(jam)
            self.samples[('lane', lane, 'queue')].append(halted)
            lane_cache[lane] = (vehicles, occupancy, halted, spill)
            for vehicle in vehicles:
                waiting = waits.get(vehicle, 0)
                increment = min(step, waiting) if vehicle not in self.previous_wait else max(0, waiting - self.previous_wait[vehicle])
                values['wait_vehicle_seconds'] += increment
                values['maximum_vehicle_wait_seconds'] = max(values['maximum_vehicle_wait_seconds'], waiting)
                values['long_wait_vehicle_seconds'] += (waiting >= threshold['long_wait_seconds']) * step
                if speeds.get(vehicle, 0) < threshold['halt_speed_meters_per_second'] and self.previous_speed.get(vehicle, 0) >= threshold['halt_speed_meters_per_second']:
                    values['stop_events'] += 1
                for tls, index, _, _ in traci.vehicle.getNextTLS(vehicle):
                    key = f'{tls}:{index}'
                    if key in self.movements and lane in self.movements[key]['incoming']:
                        next_movements[vehicle] = key
                        break
        phase_states = {m['tls_id']: traci.trafficlight.getRedYellowGreenState(m['tls_id']) for m in self.movements.values()}
        for key, movement in self.movements.items():
            values = self.movement_values[key]
            ids = [vehicle for vehicle, next_key in next_movements.items() if next_key == key]
            halted = sum(speeds.get(v, 0) < threshold['halt_speed_meters_per_second'] for v in ids)
            state = phase_states[movement['tls_id']][movement['link_index']]
            outgoing_occupancy = max((traci.lane.getLastStepOccupancy(lane) for lane in movement['outgoing']), default=0)
            downstream_halted = sum(traci.lane.getLastStepHaltingNumber(lane) for lane in movement['outgoing'])
            values['queue_vehicle_seconds'] += halted * step
            values['peak_halted_vehicles'] = max(values['peak_halted_vehicles'], halted)
            values['active_vehicle_seconds'] += len(ids) * step
            values['green_seconds'] += (state in 'Gg') * step
            values['red_seconds'] += (state in 'rR') * step
            values['yellow_seconds'] += (state in 'yY') * step
            values['unused_green_seconds'] += (state in 'Gg' and not ids) * step
            blocked = bool(state in 'Gg' and halted and outgoing_occupancy >= threshold['downstream_occupancy_percent'])
            values['green_with_blocked_downstream_seconds'] += blocked * step
            values['maximum_downstream_occupancy_percent'] = max(values['maximum_downstream_occupancy_percent'], outgoing_occupancy)
            values['queue_pressure_vehicle_seconds'] += (halted - downstream_halted) * step
            streak = values.get('current_red_seconds', 0) + step if state in 'rR' else 0
            values['current_red_seconds'] = streak
            values['maximum_continuous_red_seconds'] = max(values['maximum_continuous_red_seconds'], streak)
            for vehicle in ids:
                waiting = waits.get(vehicle, 0)
                increment = min(step, waiting) if self.previous_presence.get(vehicle) != key else max(0, waiting - self.previous_wait.get(vehicle, 0))
                values['wait_vehicle_seconds'] += increment
                values['maximum_vehicle_wait_seconds'] = max(values['maximum_vehicle_wait_seconds'], waiting)
            for detector in self.movement_detectors[key]:
                self.passed[key].update(data[0] for data in traci.inductionloop.getVehicleData(detector) if data[2] >= window_start)
        if self.dynamics:
            for vehicle, speed in speeds.items():
                acceleration = traci.vehicle.getAcceleration(vehicle)
                allowed = traci.vehicle.getAllowedSpeed(vehicle)
                self.global_values['hard_braking_vehicle_seconds'] += (acceleration < -threshold['hard_braking_meters_per_second_squared']) * step
                self.global_values['speeding_vehicle_seconds'] += (allowed > 0 and speed > allowed * 1.05) * step
                if vehicle in self.previous_acceleration:
                    self.global_values['absolute_jerk_sum'] += abs(acceleration - self.previous_acceleration[vehicle]) / step
                    self.global_values['jerk_samples'] += 1
                self.previous_acceleration[vehicle] = acceleration
                leader = traci.vehicle.getLeader(vehicle, 100)
                if leader and leader[0] in speeds and speed > speeds[leader[0]]:
                    ttc = max(0, leader[1]) / (speed - speeds[leader[0]])
                    self.global_values['ttc_proxy_below_threshold_vehicle_seconds'] += (ttc < threshold['ttc_seconds']) * step
                if self.previous_speed.get(vehicle, 0) >= threshold['halt_speed_meters_per_second'] > speed:
                    self.global_values['stop_events'] += 1
        if self.options.get('collect_vehicle_classes', True):
            for vehicle, speed in speeds.items():
                if vehicle not in self.class_cache:
                    self.class_cache[vehicle] = traci.vehicle.getVehicleClass(vehicle)
                cls = self.class_cache[vehicle]
                self.class_vehicles[cls].add(vehicle)
                values = self.class_values[cls]
                values['active_vehicle_seconds'] += step
                values['vehicle_distance_meters'] += speed * step
                values['halted_vehicle_seconds'] += (speed < threshold['halt_speed_meters_per_second']) * step
                values['wait_vehicle_seconds'] += min(step, waits.get(vehicle, 0)) if vehicle not in self.previous_wait else max(0, waits.get(vehicle, 0) - self.previous_wait[vehicle])
        self.previous_wait = dict(waits)
        self.previous_speed = dict(speeds)
        self.previous_presence = next_movements
        self.previous_acceleration = {v: a for v, a in self.previous_acceleration.items() if v in speeds}
        self.class_cache = {v: c for v, c in self.class_cache.items() if v in speeds}

    def global_summary(self):
        if not self.enabled:
            return {}
        values = dict(self.global_values)
        count = values.pop('jerk_samples', 0)
        values['mean_absolute_jerk_meters_per_second_cubed'] = values.pop('absolute_jerk_sum', 0) / count if count else None
        values.update(distribution(self.samples[('global', 'queue')], 'global_queue_vehicles'))
        return values

    def class_rows(self):
        return [{'vehicle_class': cls, 'observed_unique_vehicles': len(self.class_vehicles[cls]), **dict(values),
                 'mean_speed_meters_per_second': values['vehicle_distance_meters'] / values['active_vehicle_seconds'] if values['active_vehicle_seconds'] else None}
                for cls, values in self.class_values.items()]

    def rows(self):
        lanes, movements = [], []
        for lane, geometry in self.lanes.items():
            values = dict(self.lane_values[lane])
            occupied = values.pop('occupancy_percent_seconds', 0)
            lanes.append({**geometry, **values, 'measured_seconds': self.seconds,
                          'mean_density_vehicles_per_kilometer': values.get('active_vehicle_seconds', 0) / self.seconds * 1000 / geometry['length_meters'] if self.seconds and geometry['length_meters'] > 0 else None,
                          'mean_speed_meters_per_second': values.get('vehicle_distance_meters', 0) / values['active_vehicle_seconds'] if values.get('active_vehicle_seconds') else None,
                          'mean_occupancy_percent': occupied / self.seconds if self.seconds else None,
                          **distribution(self.samples[('lane', lane, 'jam')], 'jam_length_meters'),
                          **distribution(self.samples[('lane', lane, 'queue')], 'queue_vehicles')})
        for key, movement in self.movements.items():
            values = {k: v for k, v in self.movement_values[key].items() if k != 'current_red_seconds'}
            crossings = len(self.passed[key]) if movement['movement_flow_available'] else None
            movements.append({**{k: v for k, v in movement.items() if k not in ('incoming', 'outgoing', 'via')},
                              'incoming_lanes': '|'.join(sorted(movement['incoming'])), 'outgoing_lanes': '|'.join(sorted(movement['outgoing'])),
                              **values, 'measured_seconds': self.seconds, 'passed_vehicles': crossings,
                              'throughput_vehicles_per_hour': crossings * 3600 / self.seconds if crossings is not None and self.seconds else None,
                              'green_utilization_percent': (1 - values.get('unused_green_seconds', 0) / values['green_seconds']) * 100 if values.get('green_seconds') else None})
            movements[-1]['discharge_vehicles_per_green_hour'] = crossings * 3600 / values['green_seconds'] if crossings is not None and values.get('green_seconds') else None
        return lanes, movements
