"""Ajustes de duração do programa inicial, sem alterar os estados das fases."""
import hashlib
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET

from semaforos.cenario.experimental import digest
from semaforos.cenario.rede import phase_kind


def minimum_phase_seconds(config, key, kind):
    experimental = config['experimental']
    if kind == 'green':
        return max(config['training']['minimum_green_seconds'], experimental['green_floors'][key])
    training_key = 'minimum_yellow_seconds' if kind == 'yellow' else 'minimum_all_red_seconds'
    return max(config['training'][training_key], experimental['minimum_durations'][key])


def adjusted_programs(config, programs, edits):
    if not edits:
        return programs
    if config.get('experimental', {}).get('method') != 'compatible_groups_v2':
        raise ValueError('Prepare a rede com grupos compatíveis para editar o ciclo inicial.')
    targets = {target['tls_id'] for target in config['targets']}
    step = float(config['step_seconds'])
    updated = dict(programs)
    changed = set()
    for key, value in edits.items():
        tls, separator, index = key.rpartition(':')
        if tls not in targets or not separator or not index.isdecimal() or int(index) >= len(programs[tls]):
            raise ValueError('A fase selecionada não pertence a este cenário.')
        index = int(index)
        phase = programs[tls][index]
        minimum = minimum_phase_seconds(config, key, phase_kind(phase['state']))
        if value is None or not math.isfinite(value) or value < minimum:
            raise ValueError(f'Informe pelo menos {minimum:g} s para a fase selecionada.')
        if abs(value / step - round(value / step)) > 1e-7:
            raise ValueError(f'Use tempos em múltiplos de {step:g} s.')
        if tls not in changed:
            updated[tls] = list(programs[tls])
            changed.add(tls)
        updated[tls][index] = {**phase, 'duration': float(value)}
    cap = config.get('control', config['ppo']).get('maximum_cycle_seconds')
    if cap is not None and any(sum(p['duration'] for p in updated[tls]) > cap for tls in changed):
        raise ValueError(f'A soma dos tempos do ciclo não pode passar de {cap:g} s neste cenário.')
    return updated


def include_adjusted_times(control, programs, edits):
    bounds = control['phase_duration_bounds']
    for key, value in edits.items():
        tls, index = key.rsplit(':', 1)
        kind = phase_kind(programs[tls][int(index)]['state'])
        if kind == 'green':
            current = bounds[key]
            if current['minimum_seconds'] <= current['maximum_seconds']:
                current['minimum_seconds'] = min(current['minimum_seconds'], value)
                current['maximum_seconds'] = max(current['maximum_seconds'], value)
        else:
            bounds[key] = {'minimum_seconds': value, 'maximum_seconds': value}
            limits = control.setdefault('duration_limits', {}).setdefault(kind, {})
            limits['maximum_seconds'] = max(limits.get('maximum_seconds', value), value)


def save_adjusted_network(config, edits, directory):
    """Gera uma rede identificada pelo cenário de origem e pelos tempos aplicados."""
    source = Path(config['network'])
    identity = hashlib.sha256(json.dumps(
        [config['experimental']['network_sha256'], edits], sort_keys=True).encode()).hexdigest()
    destination = Path(directory) / f'{identity}.net.xml'
    if not destination.is_file():
        tree = ET.parse(source)
        for logic in tree.getroot().findall('tlLogic'):
            for index, phase in enumerate(logic.findall('phase')):
                value = edits.get(f"{logic.get('id')}:{index}")
                if value is not None:
                    phase.set('duration', str(float(value)))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                tree.write(temporary, encoding='utf-8', xml_declaration=True)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    config['network'] = str(destination.resolve())
    config['experimental'] = {**config['experimental'], 'network_sha256': digest(destination)}
