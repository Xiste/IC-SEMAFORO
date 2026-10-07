"""Espera e atendimento de pessoas, independentes da recompensa do algoritmo."""
import traci


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

    def sample(self):
        now = traci.simulation.getTime()
        departing = traci.simulation.getDepartedPersonIDList()
        arriving = traci.simulation.getArrivedPersonIDList()
        self.departed += len(departing)
        self.arrived += len(arriving)
        for person in departing:
            self.starts[person] = now
        for person in arriving:
            if person in self.starts:
                self.travel_times.append(now - self.starts.pop(person))
        current = {}
        self.waiting_now = 0
        for person in traci.person.getIDList():
            waiting = traci.person.getWaitingTime(person)
            increment = max(0, waiting - self.previous_wait.get(person, 0))
            self.wait += increment
            self.peak_wait = max(self.peak_wait, waiting)
            self.waiting_now += waiting > 0
            current[person] = waiting
            road = traci.person.getRoadID(person)
            parts = person.split('_')
            expected = self.expected_crossings.get(int(parts[1])) if len(parts) == 3 and parts[0] == 'ped' and parts[1].isdigit() else None
            if expected in self.crossings and road in self.waiting_areas.get(expected, set()):
                self.crossing_wait[expected] += increment
            if road in self.crossings:
                self.passages.add((person, road))
        self.previous_wait = current

    def summary(self):
        return {'planned_pedestrians': self.planned, 'pedestrians_departed': self.departed,
                'pedestrians_arrived': self.arrived, 'pedestrians_unfinished': max(0, self.departed - self.arrived),
                'pedestrians_pending': max(0, self.planned - self.departed),
                'pedestrian_wait_person_seconds': self.wait, 'pedestrians_waiting_now': self.waiting_now,
                'maximum_pedestrian_wait_seconds': self.peak_wait,
                'crossing_passages': len(self.passages),
                'mean_pedestrian_travel_time_seconds': sum(self.travel_times) / len(self.travel_times) if self.travel_times else None}

    def rows(self):
        return [{'crossing_id': edge, 'intersection': name,
                 'pedestrian_wait_person_seconds': self.crossing_wait[edge],
                 'crossing_passages': sum(crossing == edge for _, crossing in self.passages)}
                for edge, name in self.crossings.items()]
