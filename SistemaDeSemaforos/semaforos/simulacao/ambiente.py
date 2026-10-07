"""Ambiente Gymnasium com controle de durações das fases existentes pelo TraCI."""

import json
import csv
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import gymnasium as gym
import numpy as np
import psutil
import traci
from gymnasium import spaces

from semaforos.cenario.configuracao import sumo_executable, control_parameters
from semaforos.cenario.demanda import create_demand
from semaforos.relatorios.metricas import planned_vehicle_count
from semaforos.cenario.mapeamento import mapping_report, require_validated_targets
from semaforos.cenario.rede import phase_bounds, phase_kind, phase_action_spec
from semaforos.simulacao.execucao import load_scenario
from semaforos.simulacao.contagens import FlowCounts
from semaforos.cenario.pedestres import create_pedestrian_demand
from semaforos.simulacao.pedestres import PedestrianMetrics
from semaforos.simulacao.observacao import IntersectionMetrics, LiveMetrics
from semaforos.arquivos import write_json
from semaforos.relatorios.metricas import trip_summary


class SemaforosEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, config, output, gui=False, demand_config=None):
        super().__init__()
        self.config = config
        self.demand_config = demand_config if demand_config is not None else config
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        _, self.network, self.programs = load_scenario(config)
        self.targets = config["targets"]
        if not self.targets:
            raise ValueError("PPO precisa de ao menos um semáforo mapeado")
        if len(self.targets) > 1:
            if config.get("experimental"):
                from semaforos.cenario.experimental import validate_experimental
                validate_experimental(config)
            else:
                require_validated_targets(config, mapping_report(config, config.get("mapping_path")))
        self.action_mode, self.action_spec = phase_action_spec(config, self.programs)
        if self.action_mode == "green_extension":
            for target in self.targets:
                for index in target["phase_indices"]:
                    if phase_kind(self.programs[target["tls_id"]][index]["state"]) != "green":
                        raise ValueError("green_extension só pode atuar em fases verdes")
        self.interval = float(control_parameters(config).get("decision_seconds", 5))
        self.step_length = float(config["step_seconds"])
        if self.interval < self.step_length:
            raise ValueError("decision_seconds deve ser >= step_seconds")
        self.gui = gui
        self.action_space = spaces.MultiDiscrete([3] * len(self.action_spec))
        # Por sinal: fila, veículos, velocidade, índice da fase, tempo nela e restante.
        self.observation_space = spaces.Box(0, 1, shape=(6 * len(self.targets),), dtype=np.float32)
        self.connected = False
        self.episode = 0
        self.seed_value = None
        self.lanes = {}
        self.phase = {}
        self.phase_since = {}
        self.shortened = {}
        self.departed = self.arrived = 0
        self.wait_seconds = self.queue_seconds = self.vehicle_seconds = 0.0
        self.previous_wait = {}
        self.signal_metrics = {}
        self.planned = {}
        self.co2_mg = self.fuel_mg = 0.0
        self.extra_emissions = {}
        self.global_halted_seconds = 0.0
        self.global_peak_halted = 0
        self.teleports = self.collisions = 0
        self.peak_rss_mb = self.cpu_seconds = 0.0
        self.cpu_at_reset = 0.0
        self.real_started = None
        self.current_output = None
        self.action_log = []
        self.duration_applied = set()
        self.desired_durations = {}
        self.flow_counts = None
        self.last_info = None
        self.reward_total = 0.0

    def _resources(self):
        process = psutil.Process()
        processes = [process] + process.children(recursive=True)
        rss = cpu = 0.0
        for item in processes:
            try:
                rss += item.memory_info().rss
                times = item.cpu_times()
                cpu += times.user + times.system
            except psutil.Error:
                pass
        self.peak_rss_mb = max(self.peak_rss_mb, rss / 1024**2)
        self.cpu_seconds = max(self.cpu_seconds, cpu - self.cpu_at_reset)
        return cpu

    def _observation(self):
        values = []
        now = traci.simulation.getTime()
        for target in self.targets:
            tls_id = target["tls_id"]
            lanes = self.lanes[tls_id]
            halted = sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
            count = sum(traci.lane.getLastStepVehicleNumber(lane) for lane in lanes)
            speeds = [traci.lane.getLastStepMeanSpeed(lane) for lane in lanes]
            mean_speed = sum(max(0, speed) for speed in speeds) / max(1, len(speeds))
            index = traci.trafficlight.getPhase(tls_id)
            remaining = max(0, traci.trafficlight.getNextSwitch(tls_id) - now)
            elapsed = now - self.phase_since[tls_id]
            values.extend((min(1, halted / max(1, 20 * len(lanes))),
                           min(1, count / max(1, 20 * len(lanes))),
                           min(1, mean_speed / 20),
                           index / max(1, len(self.programs[tls_id]) - 1),
                           min(1, elapsed / 60), min(1, remaining / 60)))
        return np.asarray(values, dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.close()
        self.seed_value = int(seed if seed is not None else self.np_random.integers(0, 2**31 - 1))
        self.episode += 1
        folder = self.output / f"episode_{self.episode:05d}_{uuid.uuid4().hex[:8]}"
        folder.mkdir()
        self.current_output = folder
        self.real_started = time.perf_counter()
        routes = create_demand(self.demand_config, self.network, folder, self.seed_value)
        pedestrian_routes, planned_people = create_pedestrian_demand(self.demand_config, folder)
        self.planned = planned_vehicle_count(routes)
        binary = sumo_executable()
        if self.gui:
            binary = binary.with_name("sumo-gui.exe")
            if not binary.is_file():
                raise RuntimeError("sumo-gui não encontrado")
        route_files = str(routes) + ("," + str(pedestrian_routes) if pedestrian_routes else "")
        command = [str(binary), "-n", str(self.config["network"]), "-r", route_files,
                   "--step-length", str(self.step_length), "--seed", str(self.seed_value),
                   "--tripinfo-output", str(folder / "tripinfo.xml"),
                   "--tripinfo-output.write-unfinished", "true", "--no-step-log", "true"]
        self.flow_counts = FlowCounts(self.config, self.network, folder)
        if self.flow_counts.file:
            command.extend(["--additional-files", str(self.flow_counts.file)])
        if self.gui:
            delay = float(control_parameters(self.config).get('gui_delay_milliseconds', 0))
            if not 0 <= delay <= 2000:
                raise ValueError('Atraso do SUMO-GUI deve ficar entre 0 e 2000 ms')
            command.extend(["--start", "--quit-on-end", '--delay', str(delay)])
        (folder / "run_config.json").write_text(json.dumps({
            "sumo_command": command, "seed": self.seed_value,
            "effective_config": self.config,
            "targets": self.targets, "objectives": self.config.get("objectives"),
            "ppo": self.config.get("ppo"), "metrics": self.config.get("metrics"),
            "planned": self.planned,
            "action_mode": self.action_mode, "action_spec": self.action_spec,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            self.last_info = None
            traci.start(command)
            self.connected = True
            self.lanes = {target["tls_id"]: sorted(set(traci.trafficlight.getControlledLanes(target["tls_id"])))
                          for target in self.targets}
            self.phase = {target["tls_id"]: traci.trafficlight.getPhase(target["tls_id"])
                          for target in self.targets}
            self.phase_since = {target["tls_id"]: traci.simulation.getTime() for target in self.targets}
            self.shortened = {target["tls_id"]: False for target in self.targets}
            self.intersection_metrics = IntersectionMetrics(self.targets, self.lanes, self.step_length)
            root = ET.parse(self.config['network']).getroot()
            names = {t['tls_id']: t['name'] for t in self.targets}
            crossings = {e.get('id') for e in root.findall('edge') if e.get('function') == 'crossing'}
            crossing_owners = {}
            for c in root.findall('connection'):
                if c.get('tl') in names:
                    for side in ('from', 'to'):
                        if c.get(side) in crossings:
                            crossing_owners[c.get(side)] = names[c.get('tl')]
            waiting_areas = {edge: {c.get('from') for c in root.findall('connection') if c.get('to') == edge}
                             for edge in crossing_owners}
            self.pedestrian_metrics = PedestrianMetrics(planned_people, self.step_length, crossing_owners,
                                                       self.demand_config.get('pedestrians', {}).get('flows', []), waiting_areas)
            self.live_metrics = LiveMetrics(folder, self.episode, self.seed_value, self.output.parent)
            self.reward_total = 0.0
            self.departed = self.arrived = 0
            self.wait_seconds = self.queue_seconds = self.vehicle_seconds = 0.0
            self.previous_wait = {}
            self.signal_metrics = {target["tls_id"]: {
                "queue_vehicle_seconds": 0.0, "peak_halted_vehicles": 0,
                "speed_meters_per_second_sum": 0.0, "occupancy_percent_sum": 0.0,
                "lane_samples": 0, "phase_seconds": {str(i): 0.0 for i in range(len(self.programs[target["tls_id"]]))},
            } for target in self.targets}
            self.co2_mg = self.fuel_mg = 0.0
            self.extra_emissions = {key: 0.0 for key in ("co_grams", "hc_grams", "nox_grams", "pmx_grams", "electricity_wh")}
            self.global_halted_seconds = 0.0
            self.global_peak_halted = 0
            self.teleports = self.collisions = 0
            self.peak_rss_mb = self.cpu_seconds = 0.0
            self.cpu_at_reset = self._resources()
            self.cpu_seconds = 0.0
            self.action_log = []
            self.duration_applied = set()
            self.desired_durations = {}
            return self._observation(), {"seed": self.seed_value, "output": str(folder)}
        except Exception:
            self.close()
            raise

    def _apply_phase_durations(self):
        # Aplicar na entrada da fase permite controlar amarelos/vermelhos mais
        # curtos que o intervalo entre decisões, sem saltar estados do programa.
        for target in self.targets:
            tls_id = target["tls_id"]
            index = traci.trafficlight.getPhase(tls_id)
            key = (tls_id, index)
            if key not in self.desired_durations or tls_id in self.duration_applied:
                continue
            choice, desired = self.desired_durations[key]
            elapsed = traci.trafficlight.getSpentDuration(tls_id)
            remaining = max(0.0, desired - elapsed)
            before = traci.trafficlight.getNextSwitch(tls_id) - traci.simulation.getTime()
            traci.trafficlight.setPhaseDuration(tls_id, remaining)
            self.duration_applied.add(tls_id)
            if self.config.get("metrics", {}).get("collect_actions", True):
                self.action_log.append({"time_seconds": traci.simulation.getTime(), "tls_id": tls_id,
                    "phase_index": index, "phase_kind": phase_kind(self.programs[tls_id][index]["state"]),
                    "action": choice, "phase_elapsed_seconds": elapsed,
                    "phase_started_seconds": traci.simulation.getTime() - elapsed,
                    "remaining_seconds_before_action": before,
                    "selected_total_duration_seconds": desired,
                    "applied_phase_duration_seconds": remaining})

    def step(self, action):
        if not self.connected:
            raise RuntimeError("Chame reset antes de step")
        action = np.asarray(action)
        if not self.action_space.contains(action):
            raise ValueError(f"Ação inválida: {action}")
        if self.action_mode == "phase_durations":
            self.desired_durations = {(item["tls_id"], item["phase_index"]):
                                      (int(choice), item["durations_seconds"][int(choice)])
                                      for item, choice in zip(self.action_spec, action)}
            self._apply_phase_durations()
        now = traci.simulation.getTime()
        for target, choice in zip(self.targets, action if self.action_mode == "green_extension" else []):
            tls_id = target["tls_id"]
            index = traci.trafficlight.getPhase(tls_id)
            if index not in target["phase_indices"] or self.shortened[tls_id]:
                continue
            lower, upper = phase_bounds(self.config, self.programs[tls_id][index])
            elapsed = now - self.phase_since[tls_id]
            remaining = traci.trafficlight.getNextSwitch(tls_id) - now
            applied_duration = None
            # 0 encerra o verde após o mínimo; 1 mantém; 2 estende até o máximo.
            if choice == 0 and elapsed >= lower:
                traci.trafficlight.setPhaseDuration(tls_id, self.step_length)
                applied_duration = self.step_length
                self.shortened[tls_id] = True
            elif (choice == 2 and remaining <= self.interval
                  and elapsed + remaining + self.interval + self.step_length <= upper):
                traci.trafficlight.setPhaseDuration(tls_id, remaining + self.interval)
                applied_duration = remaining + self.interval
            if self.config.get("metrics", {}).get("collect_actions", True):
                self.action_log.append({"time_seconds": now, "tls_id": tls_id,
                                        "phase_index": index, "action": int(choice),
                                        "phase_elapsed_seconds": elapsed,
                                        "remaining_seconds_before_action": remaining,
                                        "applied_phase_duration_seconds": applied_duration})
        wait = queue = active = 0.0
        metric_options = self.config.get("metrics", {})
        end = min(float(self.config["duration_seconds"]), now + self.interval)
        while traci.simulation.getTime() < end:
            traci.simulationStep()
            self.flow_counts.step()
            self.pedestrian_metrics.sample()
            self.intersection_metrics.sample(metric_options.get('collect_lane_details', True))
            current = traci.simulation.getTime()
            self.departed += traci.simulation.getDepartedNumber()
            self.arrived += traci.simulation.getArrivedNumber()
            vehicle_ids = traci.vehicle.getIDList()
            active += len(vehicle_ids) * self.step_length
            global_halted = sum(traci.vehicle.getSpeed(vehicle) < 0.1 for vehicle in vehicle_ids)
            self.global_halted_seconds += global_halted * self.step_length
            self.global_peak_halted = max(self.global_peak_halted, global_halted)
            if metric_options.get("collect_emissions", False):
                self.co2_mg += sum(max(0, traci.vehicle.getCO2Emission(vehicle))
                                   for vehicle in vehicle_ids) * self.step_length
                self.fuel_mg += sum(max(0, traci.vehicle.getFuelConsumption(vehicle))
                                    for vehicle in vehicle_ids) * self.step_length
                for key, getter, factor in (
                    ("co_grams", traci.vehicle.getCOEmission, 1 / 1000),
                    ("hc_grams", traci.vehicle.getHCEmission, 1 / 1000),
                    ("nox_grams", traci.vehicle.getNOxEmission, 1 / 1000),
                    ("pmx_grams", traci.vehicle.getPMxEmission, 1 / 1000),
                    ("electricity_wh", traci.vehicle.getElectricityConsumption, 1),
                ):
                    self.extra_emissions[key] += sum(max(0, getter(vehicle)) for vehicle in vehicle_ids) * self.step_length * factor
            if metric_options.get("collect_events", True):
                self.teleports += traci.simulation.getStartingTeleportNumber()
                self.collisions += traci.simulation.getCollidingVehiclesNumber()
            current_wait = {vehicle: traci.vehicle.getWaitingTime(vehicle) for vehicle in vehicle_ids}
            wait += sum(max(0, value - self.previous_wait.get(vehicle, 0))
                        for vehicle, value in current_wait.items())
            self.previous_wait = current_wait
            for target in self.targets:
                tls_id = target["tls_id"]
                halted = sum(traci.lane.getLastStepHaltingNumber(lane) for lane in self.lanes[tls_id])
                queue += halted * self.step_length
                signal = self.signal_metrics[tls_id]
                signal["queue_vehicle_seconds"] += halted * self.step_length
                signal["peak_halted_vehicles"] = max(signal["peak_halted_vehicles"], halted)
                if metric_options.get("collect_lane_details", True):
                    for lane in self.lanes[tls_id]:
                        speed = traci.lane.getLastStepMeanSpeed(lane)
                        if speed >= 0:
                            signal["speed_meters_per_second_sum"] += speed
                            signal["occupancy_percent_sum"] += traci.lane.getLastStepOccupancy(lane)
                            signal["lane_samples"] += 1
                index = traci.trafficlight.getPhase(tls_id)
                signal["phase_seconds"][str(index)] += self.step_length
                if index != self.phase[tls_id]:
                    self.phase[tls_id] = index
                    self.phase_since[tls_id] = current
                    self.shortened[tls_id] = False
                    self.duration_applied.discard(tls_id)
            if self.action_mode == "phase_durations":
                self._apply_phase_durations()
        self.wait_seconds += wait
        self.queue_seconds += queue
        self.vehicle_seconds += active
        weights = self.config.get("objectives", {"waiting": 1, "queues": 1, "travel": 1})
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Ao menos um peso de objetivo deve ser positivo")
        # Escalas explícitas do piloto; a calibração definitiva usará a referência.
        reward = -(weights["waiting"] * wait / 60 + weights["queues"] * queue / 60
                   + weights["travel"] * active / 600) / total
        done = traci.simulation.getTime() >= self.config["duration_seconds"]
        info = {"simulated_seconds": traci.simulation.getTime(), "departed": self.departed,
                "arrived": self.arrived, "wait_vehicle_seconds": self.wait_seconds,
                "queue_vehicle_seconds": self.queue_seconds,
                "global_halted_vehicle_seconds": self.global_halted_seconds,
                "global_peak_halted_vehicles": self.global_peak_halted,
                "active_vehicle_seconds": self.vehicle_seconds}
        if done:
            info = self.snapshot(complete=True)
            reward -= (info['unfinished'] + info['pending_departure']) * self.config['training']['unfinished_penalty_seconds'] / 600
        elif metric_options.get('collect_resources', True):
            self._resources()
        self.reward_total += float(reward)
        self.last_info = info
        self.live_metrics.record(info, float(reward), self.intersection_metrics, self.pedestrian_metrics.summary())
        return self._observation(), float(reward), bool(done), False, info

    def snapshot(self, complete=False):
        """Captura também episódios parciais antes de fechar a conexão TraCI."""
        unfinished = max(0, self.departed - self.arrived)
        people = self.pedestrian_metrics.summary()
        pending = max(0, traci.simulation.getMinExpectedNumber() - unfinished
                      - people['pedestrians_unfinished'] - people['pedestrians_pending'])
        info = {'episode_complete': bool(complete), 'episode_output': str(self.current_output),
                'episode_number': self.episode, 'simulated_seconds': traci.simulation.getTime(),
                'seed': self.seed_value, 'departed': self.departed, 'arrived': self.arrived,
                'unfinished': unfinished, 'pending_departure': pending,
                'wait_vehicle_seconds': self.wait_seconds, 'queue_vehicle_seconds': self.queue_seconds,
                'global_halted_vehicle_seconds': self.global_halted_seconds,
                'global_peak_halted_vehicles': self.global_peak_halted,
                'active_vehicle_seconds': self.vehicle_seconds, **self.planned, **people,
                'flow_counts': self.flow_counts.rows(traci.simulation.getTime()),
                'intersections': self.intersection_metrics.rows(),
                'pedestrian_crossings': self.pedestrian_metrics.rows(),
                'real_seconds': round(time.perf_counter() - self.real_started, 3)}
        metric_options = self.config.get('metrics', {})
        info["signals"] = {tls_id: {
            "queue_vehicle_seconds": values["queue_vehicle_seconds"],
            "peak_halted_vehicles": values["peak_halted_vehicles"],
            "mean_lane_speed_meters_per_second": (
                values["speed_meters_per_second_sum"] / values["lane_samples"]
                if values["lane_samples"] else None),
            "mean_lane_occupancy_percent": (
                values["occupancy_percent_sum"] / values["lane_samples"]
                if values["lane_samples"] else None),
            "phase_seconds": values["phase_seconds"],
        } for tls_id, values in self.signal_metrics.items()}
        if metric_options.get("collect_emissions", False):
            info.update(co2_grams=self.co2_mg / 1000, fuel_grams=self.fuel_mg / 1000)
            info.update(self.extra_emissions)
        if metric_options.get("collect_events", True):
            info.update(teleports_started=self.teleports, collision_vehicles=self.collisions)
        if metric_options.get("collect_resources", True):
            self._resources()
            info.update(peak_rss_mb=round(self.peak_rss_mb, 2),
                        cpu_seconds=round(self.cpu_seconds, 3))
        return info

    def close(self):
        if not self.connected:
            return
        info = None
        try:
            if self.last_info is not None:
                info = self.snapshot(complete=traci.simulation.getTime() >= self.config['duration_seconds'])
            traci.close()
        finally:
            self.connected = False
        if info is not None:
            info['reward'] = self.reward_total
            info.update(trip_summary(self.current_output / 'tripinfo.xml'))
            self.last_info = info
            write_json(self.current_output / 'episode_metrics.json', info)
            if self.action_log:
                with (self.current_output / 'actions.csv').open('w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=self.action_log[0])
                    writer.writeheader()
                    writer.writerows(self.action_log)
