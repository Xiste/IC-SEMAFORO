"""Espera e atendimento de pessoas, independentes da recompensa do algoritmo."""
import traci
from semaforos.simulacao.detalhes import distribution


class PedestrianMetrics:
    def __init__(self, planned, step, crossings, flows=(), waiting_areas=None):
        self.planned, self.step = planned, step
        self.crossings = crossings
        self.departed = self.arrived = 0
        self.wait = 0.0
        self.previous_wait = {}
        self.passages = set()
        self.crossing_wait = {edge: 0.0 for edge in crossings}
        self.expected_crossings = {index: flow.get('crossing_id') for index, flow in enumerate(flows)}
        self.waiting_areas = waiting_areas or {}
        self.peak_wait = 0.0
        self.starts = {}
        self.travel_times = []
        self.waiting_now = 0
        self.total_departed = 0
        self.active_at_window_end = self.pending_at_window_end = 0
        self.previous_road = {}
        self.crossing_peak_wait = {edge: 0.0 for edge in crossings}
        self.walking_seconds = self.active_seconds = 0.0

    def sample(self, measure=True):
        now = traci.simulation.getTime()
        departing = traci.simulation.getDepartedPersonIDList()
        arriving = traci.simulation.getArrivedPersonIDList()
        self.total_departed += len(departing)
        if measure:
            self.departed += len(departing)
            self.arrived += len(arriving)
        for person in departing:
            self.starts[person] = now
        for person in arriving:
            if person in self.starts:
                elapsed = now - self.starts.pop(person)
                if measure:
                    self.travel_times.append(elapsed)
        current = {}
        people = traci.person.getIDList()
        if measure:
            self.waiting_now = 0
            self.active_at_window_end = len(people)
            self.pending_at_window_end = max(0, self.planned - self.total_departed)
            self.active_seconds += len(people) * self.step
        roads = {}
        for person in people:
            waiting = traci.person.getWaitingTime(person)
            increment = max(0, waiting - self.previous_wait.get(person, 0))
            if measure:
                self.wait += increment
                self.peak_wait = max(self.peak_wait, waiting)
                self.waiting_now += waiting > 0
                self.walking_seconds += (traci.person.getSpeed(person) > .1) * self.step
            current[person] = waiting
            road = traci.person.getRoadID(person)
            roads[person] = road
            parts = person.split('_')
            expected = self.expected_crossings.get(int(parts[1])) if len(parts) == 3 and parts[0] == 'ped' and parts[1].isdigit() else None
            if measure and expected in self.crossings and road in self.waiting_areas.get(expected, set()):
                self.crossing_wait[expected] += increment
                self.crossing_peak_wait[expected] = max(self.crossing_peak_wait[expected], waiting)
            if measure and road in self.crossings and self.previous_road.get(person) != road:
                self.passages.add((person, road))
        self.previous_wait = current
        self.previous_road = roads

    def summary(self):
        return {'planned_pedestrians': self.planned, 'pedestrians_departed': self.departed,
                'pedestrians_arrived': self.arrived, 'pedestrians_unfinished': self.active_at_window_end,
                'pedestrians_pending': self.pending_at_window_end,
                'pedestrian_wait_person_seconds': self.wait, 'pedestrians_waiting_now': self.waiting_now,
                'maximum_pedestrian_wait_seconds': self.peak_wait,
                'crossing_passages': len(self.passages),
                'active_person_seconds': self.active_seconds, 'walking_person_seconds': self.walking_seconds,
                **distribution(self.travel_times, 'pedestrian_travel_time_seconds')}

    def rows(self):
        return [{'crossing_id': edge, 'intersection': name,
                 'pedestrian_wait_person_seconds': self.crossing_wait[edge],
                 'maximum_pedestrian_wait_seconds': self.crossing_peak_wait[edge],
                 'crossing_passages': sum(crossing == edge for _, crossing in self.passages)}
                for edge, name in self.crossings.items()]
