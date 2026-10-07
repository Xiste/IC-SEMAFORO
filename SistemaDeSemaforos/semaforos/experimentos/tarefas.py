"""Processos de execução com estado persistente para reconectar a interface."""
import argparse
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psutil

from semaforos.arquivos import read_json, write_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config


COMMANDS = {'rl-train', 'rl-eval', 'run-reference'}
LOCAL_PROCESSES = {}


def cancellation_requested(output):
    output = Path(output)
    return (output / 'cancel.flag').exists() or (output.parent / 'cancel.flag').exists()


def start_job(config, command, results, model=None):
    if command not in COMMANDS:
        raise ValueError('Comando de execução não suportado')
    folder = Path(results) / f'ui_{uuid4().hex[:12]}'
    folder.mkdir(parents=True)
    config_path = folder / 'cenario.json'
    write_json(config_path, config)
    read_config(config_path)
    write_json(folder / 'job.json', {'command': command, 'status': 'starting', 'created_at': time.time(),
                                    'model': str(model) if model else None})
    with (folder / 'processo.log').open('w', encoding='utf-8') as log:
        try:
            process = subprocess.Popen([sys.executable, '-m', 'semaforos.experimentos.tarefas', '--folder', str(folder)],
                             cwd=PROJECT_ROOT, stdout=log, stderr=subprocess.STDOUT,
                             env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            LOCAL_PROCESSES[str(folder)] = process
        except Exception as error:
            write_json(folder / 'job.json', {'command': command, 'status': 'failed', 'error': str(error), 'exit_code': 1})
            raise
    return job_paths(folder)


def job_paths(folder):
    folder = Path(folder)
    return {'folder': folder, 'output': folder / 'execucao', 'log': folder / 'processo.log'}


def job_state(job):
    process = LOCAL_PROCESSES.get(str(job['folder']))
    if process is not None and process.poll() is not None:
        LOCAL_PROCESSES.pop(str(job['folder']), None)
    state = read_json(job['folder'] / 'job.json') or {'status': 'unknown'}
    if state['status'] == 'running':
        try:
            process = psutil.Process(state['pid'])
            if abs(process.create_time() - state['process_created_at']) > 0.1 or not process.is_running():
                return {**state, 'status': 'interrupted'}
        except psutil.Error:
            return {**state, 'status': 'interrupted'}
    if state['status'] == 'starting' and time.time() - state.get('created_at', 0) > 90:
        return {**state, 'status': 'failed', 'error': 'O processo não iniciou; consulte o log.'}
    return state


def saved_jobs(results):
    return [job_paths(path.parent) for path in sorted(Path(results).glob('ui_*/job.json'), key=lambda p: p.stat().st_mtime, reverse=True)]


def execute(folder):
    folder = Path(folder).resolve()
    state = read_json(folder / 'job.json')
    if not state or state['command'] not in COMMANDS or state.get('status') != 'starting':
        raise ValueError('Execução ausente, inválida ou já iniciada')
    state.update(status='running', pid=os.getpid(), process_created_at=psutil.Process().create_time(),
                 started_at=datetime.now(timezone.utc).isoformat())
    write_json(folder / 'job.json', state)
    code = 0
    try:
        config = read_config(folder / 'cenario.json')
        output = folder / 'execucao'
        if state['command'] == 'run-reference':
            from .referencia import run_reference
            run_reference(config, output)
        else:
            from .rl import train_rl, evaluate_rl
            if state['command'] == 'rl-train':
                train_rl(config, output)
            else:
                evaluate_rl(config, output, state['model'])
        summary = read_json(output / 'summary.json') or {}
        state['status'] = 'cancelled' if summary.get('cancelled') else 'completed'
    except Exception as error:
        code = 1
        state.update(status='failed', error=str(error))
        traceback.print_exc()
    finally:
        state.update(exit_code=code, finished_at=datetime.now(timezone.utc).isoformat())
        write_json(folder / 'job.json', state)
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', required=True)
    sys.exit(execute(parser.parse_args().folder))
