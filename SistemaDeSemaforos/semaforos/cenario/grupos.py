"""Grupos protegidos conferidos contra a matriz de conflitos da rede SUMO."""
import itertools
import math
import xml.etree.ElementTree as ET


def signal_links(root, tls):
    return [c for c in root.findall("connection") if c.get("tl") == tls]


def conflict_graph(root, tls):
    connections = signal_links(root, tls)
    junction_lanes = {}
    matrices = {}
    for node in root.findall("junction"):
        requests = {int(r.get("index")): r.get("foes") for r in node.findall("request")}
        if requests:
            matrices[node.get("id")] = requests
            for index, lane in enumerate(node.get("intLanes", "").split()):
                junction_lanes[lane] = (node.get("id"), index)
    edges = {e.get("id"): e for e in root.findall("edge")}
    continuation = {f"{c.get('from')}_{c.get('fromLane')}": c.get("via")
                    for c in root.findall("connection") if c.get("from", "").startswith(":") and c.get("via")}
    links = {}
    for c in connections:
        candidates = [c.get("via")]
        via = c.get("via")
        visited = set()
        while via in continuation and via not in visited:
            visited.add(via)
            via = continuation[via]
            candidates.append(via)
        for side, lane_key in (("from", "fromLane"), ("to", "toLane")):
            if edges[c.get(side)].get("function") == "crossing":
                candidates.append(f"{c.get(side)}_{c.get(lane_key)}")
        cell = next((junction_lanes[x] for x in candidates if x in junction_lanes), None)
        if cell is None or cell[1] not in matrices[cell[0]]:
            raise ValueError(f"Matriz de conflitos não identifica {tls}:{c.get('linkIndex')}")
        links.setdefault(int(c.get("linkIndex")), []).append((cell, c))
    graph = {index: set() for index in links}
    def conflicts(a, b):
        (node_a, ia), ca = a
        (node_b, ib), cb = b
        if node_a != node_b or ia == ib:
            return False
        bits_a, bits_b = matrices[node_a][ia], matrices[node_a][ib]
        if max(ia, ib) >= min(len(bits_a), len(bits_b)):
            raise ValueError(f"Matriz incompleta no nó {node_a}")
        merge = ca.get("to") == cb.get("to") and ca.get("toLane") == cb.get("toLane") and (ca.get("from"), ca.get("fromLane")) != (cb.get("from"), cb.get("fromLane"))
        return bits_a[-ib - 1] == "1" or bits_b[-ia - 1] == "1" or merge
    for left, right in itertools.combinations(links, 2):
        if any(conflicts(a, b) for a in links[left] for b in links[right]):
            graph[left].add(right)
            graph[right].add(left)
    return graph


def compatible_groups(graph):
    groups = []
    for index in sorted(graph, key=lambda item: (-len(graph[item]), item)):
        group = next((g for g in groups if not graph[index].intersection(g)), None)
        if group is None:
            groups.append([index])
        else:
            group.append(index)
    return [sorted(group) for group in groups]


def geometric_minima(root, connections):
    edges = {edge.get("id"): edge for edge in root.findall("edge")}
    lanes = {lane.get("id"): lane for edge in edges.values() for lane in edge.findall("lane")}
    crossings = [lanes[f"{c.get(side)}_{c.get(side + 'Lane')}"]
                 for c in connections for side in ("from", "to") if edges[c.get(side)].get("function") == "crossing"]
    green = max([8] + [math.ceil(float(l.get("length")) / 0.8) + 2 for l in crossings])
    clearance = max([3] + [math.ceil(float(lanes[c.get("via")].get("length")) / 3.0) + 2
                           for c in connections if c.get("via") in lanes])
    return green, max(clearance, green) if crossings else clearance


def build_program(root, tls):
    graph = conflict_graph(root, tls)
    groups = compatible_groups(graph)
    connections = signal_links(root, tls)
    for old in list(root.findall("tlLogic")):
        if old.get("id") == tls:
            root.remove(old)
    logic = ET.SubElement(root, "tlLogic", id=tls, type="static", programID="experimental_groups", offset="0")
    durations, floors, bounds = {}, {}, {}
    width = max(graph) + 1
    for number, group in enumerate(groups):
        local = [c for c in connections if int(c.get("linkIndex")) in group]
        crossing_time, clearance = geometric_minima(root, local)
        green = max(24, crossing_time)
        floors[f"{tls}:{3 * number}"] = crossing_time
        for position, color, duration in ((0, "G", green), (1, "y", 3), (2, "r", max(3, clearance))):
            state = "".join(color if index in group and color != "r" else "r" for index in range(width))
            ET.SubElement(logic, "phase", duration=str(duration), state=state)
            key = f"{tls}:{3 * number + position}"
            durations[key] = duration
            bounds[key] = {"minimum_seconds": crossing_time if position == 0 else duration,
                           "maximum_seconds": math.ceil(green * 1.4) if position == 0 else duration + (3 if position == 1 else 2)}
    return groups, durations, floors, bounds


def audit_program(root, tls):
    graph = conflict_graph(root, tls)
    logics = [l for l in root.findall("tlLogic") if l.get("id") == tls]
    if len(logics) != 1 or set(graph) != set(range(max(graph) + 1)):
        raise ValueError(f"Programa ou índices incompletos em {tls}")
    logic = logics[0]
    phases = logic.findall("phase")
    covered = set()
    if len(phases) % 3:
        raise ValueError(f"Sequência de fases inválida em {tls}")
    for start in range(0, len(phases), 3):
        green, yellow, red = phases[start:start + 3]
        state = green.get("state")
        if any(len(p.get("state", "")) != len(graph) for p in (green, yellow, red)):
            raise ValueError(f"Estado com tamanho incorreto em {tls}")
        opened = {i for i, color in enumerate(state) if color == "G"}
        if not opened or set(state) - {"G", "r"}:
            raise ValueError(f"Estado verde inválido em {tls}")
        if any(graph[i].intersection(opened) for i in opened):
            raise ValueError(f"Movimentos conflitantes simultâneos em {tls}:{start}")
        if yellow.get("state") != state.replace("G", "y") or set(red.get("state")) != {"r"}:
            raise ValueError(f"Transição sem limpeza em {tls}:{start}")
        green_min, red_min = geometric_minima(root, [c for c in signal_links(root, tls) if int(c.get("linkIndex")) in opened])
        durations = [float(p.get("duration")) for p in (green, yellow, red)]
        if not all(math.isfinite(v) for v in durations) or durations[0] < green_min or durations[1] < 3 or durations[2] < red_min:
            raise ValueError(f"Tempos inválidos em {tls}")
        covered.update(opened)
    if covered != set(graph):
        raise ValueError(f"Movimentos sem atendimento em {tls}")
    return {"controlador": tls, "movimentos_atendidos": len(graph), "grupos": len(phases) // 3,
            "fases": len(phases), "ciclo_inicial_s": sum(float(p.get("duration")) for p in phases),
            "conflitos_simultaneos": 0}
