"""Catálogos da instalação local e parâmetros enviados pelo pipeline."""

import inspect
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import traci
from traci.domain import Domain

from semaforos.cenario.configuracao import sumo_executable
from semaforos.relatorios.metricas import TRIP_FIELDS
from semaforos.cenario.rede import network_programs, phase_action_spec
from semaforos.algoritmos.registro import get_algorithm
from semaforos.relatorios.legendas import metric_legend, parameter_legend, SUMO_CATEGORIES


def sumo_options():
    """Obtém todas as opções CLI do executável instalado, com seus comentários."""
    binary = sumo_executable()
    version = subprocess.run([str(binary), "--version"], capture_output=True,
                             text=True, check=True).stdout.splitlines()[0]
    with tempfile.TemporaryDirectory(prefix="sumo_catalogo_") as folder:
        path = Path(folder) / "template.sumocfg"
        subprocess.run([str(binary), "--save-template", str(path),
                        "--save-commented", "true"], capture_output=True, check=True)
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        # SUMO 1.27.1 inclui '--opção' em comentários, inválido na sintaxe XML.
        xml = re.sub(r"<!--(.*?)-->", lambda match: "<!--" + match[1].replace("--", "&#45;&#45;") + "-->",
                     path.read_text(encoding="utf-8"), flags=re.DOTALL)
        root = ET.fromstring(xml, parser=parser)
    rows = []
    for group in root:
        description = ""
        for option in group:
            if option.tag is ET.Comment:
                description = (option.text or "").strip().replace("&#45;&#45;", "--")
            else:
                rows.append({"categoria": group.tag, "opção": option.tag,
                             "categoria em português": SUMO_CATEGORIES.get(group.tag, group.tag),
                             "tipo": option.get("type", ""),
                             "padrão no template": option.get("value", ""),
                             "aliases": option.get("synonymes", ""),
                             "descrição SUMO": description})
                description = ""
    return version, rows


def traci_getters():
    """Inventário de consultas; inclui identificadores e estruturas, não só métricas."""
    rows = []
    for name, domain in sorted(vars(traci).items()):
        if not isinstance(domain, Domain):
            continue
        for method_name in sorted(dir(domain)):
            method = getattr(domain, method_name)
            if not method_name.startswith("get") or not callable(method):
                continue
            doc = inspect.getdoc(method) or "Sem documentação local"
            rows.append({"domínio": name, "consulta": method_name,
                         "assinatura": str(inspect.signature(method)),
                         "descrição TraCI": doc,
                         "cobertura": "API disponível; não implica coleta pelo pipeline"})
    return rows


def parameter_rows(config):
    rows = []

    def flatten(value, prefix):
        if isinstance(value, dict) and value:
            for key, item in value.items():
                flatten(item, f"{prefix}.{key}" if prefix else key)
        elif isinstance(value, list) and value:
            for index, item in enumerate(value):
                flatten(item, f"{prefix}[{index}]")
        else:
            usage = ("busca legada; não usado no PPO" if prefix in (
                "training.iterations", "training.warmup_random", "training.candidate_pool")
                else "planilha/auditoria; não substitui o programa SUMO" if prefix in ("plans", "plan_id")
                else "cenário PPO / avaliação")
            rows.append({"parâmetro": prefix,
                         "valor": json.dumps(value, ensure_ascii=False, default=str),
                         "origem": "cenário atual", "uso": usage})

    flatten(config, "")
    if Path(config["network"]).is_file():
        programs = network_programs(config["network"])
        for target in config["targets"]:
            for index, phase in enumerate(programs.get(target["tls_id"], [])):
                rows.append({"parâmetro": f"TLS.{target['tls_id']}.phase[{index}]",
                             "valor": json.dumps(phase), "origem": "programa lido da rede"})
        try:
            _, action_spec = phase_action_spec(config, programs)
            rows.append({"parâmetro": "PPO.action_spec", "valor": json.dumps(action_spec),
                         "origem": "ações derivadas das fases e limites"})
        except (ValueError, KeyError) as error:
            rows.append({"parâmetro": "PPO.action_spec", "valor": str(error),
                         "origem": "configuração inválida; treino será recusado"})
    # Todos os argumentos do construtor: os demais são padrões da SB3 instalada.
    algorithm = get_algorithm(config.get("algorithm", "PPO"))
    try:
        supplied = {"env": "SemaforosEnv", **algorithm.constructor_parameters(config)}
    except ValueError as error:
        supplied = {"env": "SemaforosEnv", **config.get(algorithm.config_key, {})}
        rows.append({"parâmetro": "algorithm.validation", "valor": str(error),
                     "origem": "configuração inválida; treino será recusado"})
    for name, argument in inspect.signature(algorithm.model_class).parameters.items():
        value = supplied.get(name, argument.default)
        rows.append({"parâmetro": f"{algorithm.name}.constructor.{name}",
                     "valor": json.dumps(value, ensure_ascii=False, default=str),
                     "origem": "argumento do pipeline" if name in supplied else "padrão SB3 instalada"})
    for name, value in {"tripinfo-output.write-unfinished": "true", "no-step-log": "true",
                        "step-length": config["step_seconds"], "seed": config["seeds"][0],
                        "net-file": str(config["network"]),
                        "route-files": "gerado por episódio",
                        "tripinfo-output": "episodes/.../tripinfo.xml"}.items():
        rows.append({"parâmetro": f"SUMO.command.{name}", "valor": str(value),
                     "origem": "comando PPO; semente muda por episódio"})
    for row in rows:
        label, description = parameter_legend(row["parâmetro"])
        row.update({"nome em português": label, "legenda em português": description})
    return rows


def metric_rows(config):
    rows = []
    options = config.get("metrics", {})

    def add(names, unit, scope, source, flag=None):
        enabled = flag is None or options.get(flag, flag != 'collect_emissions')
        if flag in ('collect_vehicle_dynamics', 'collect_vehicle_classes'):
            enabled = enabled and options.get('collect_extended', True)
        for name in names.split():
            label, description, _ = metric_legend(name)
            rows.append({"métrica": name, "nome em português": label,
                         "legenda em português": description, "unidade": unit, "escopo": scope,
                         "fonte": source, "coleta": "habilitada" if enabled
                         else "opcional desabilitada"})

    add("planned_vehicles departed arrived unfinished pending_departure tripinfo_completed tripinfo_unfinished",
        "veículos", "episódio", "demanda / TraCI / tripinfo")
    add("simulated_seconds real_seconds", "s", "episódio", "TraCI / relógio")
    add("wait_vehicle_seconds active_vehicle_seconds global_halted_vehicle_seconds",
        "veículo·s", "rede inteira", "integração por passo TraCI")
    add("queue_vehicle_seconds", "veículo·s", "entradas dos alvos", "TraCI lane")
    add('controller_count unique_lane_count', 'contagem', 'por cruzamento físico', 'união de faixas dos controladores')
    add('episode_complete', 'sim/não', 'episódio completo ou parcial', 'horizonte efetivamente atingido')
    add('planned_pedestrians pedestrians_departed pedestrians_arrived pedestrians_unfinished pedestrians_pending pedestrians_waiting_now',
        'pessoas', 'pedestres; demanda opcional', 'demanda / TraCI person e simulation')
    add('pedestrian_wait_person_seconds', 'pessoa·s', 'global e área de espera por travessia indicada na demanda', 'TraCI person')
    add('maximum_pedestrian_wait_seconds mean_pedestrian_travel_time_seconds', 's', 'pedestres; chegadas completas na média', 'TraCI person / simulation')
    add('crossing_passages', 'passagens', 'pessoa/travessia distintos', 'TraCI person road ID')
    add('measured_vehicles_per_hour fitted_vehicles_per_hour realized_vehicles_per_hour', 'veículos/h', 'trechos com contagens informadas', 'calibração / detectores E1')
    add('passed_vehicles', 'veículos', 'distintos por trecho medido', 'TraCI inductionloop')
    add('observed_seconds', 's', 'tempo efetivo de contagem', 'TraCI simulation')
    add('queue_vehicles_now', 'veículos', 'entradas por cruzamento; histórico ao vivo', 'TraCI lane')
    add('reward_step', 'valor', 'por decisão; histórico ao vivo', 'ambiente')
    add("peak_halted_vehicles", "veículos", "por alvo", "TraCI lane")
    add("global_peak_halted_vehicles", "veículos", "rede inteira", "TraCI vehicle")
    add("mean_lane_speed_meters_per_second", "m/s", "por alvo; média simples das amostras",
        "TraCI lane", "collect_lane_details")
    add("mean_lane_occupancy_percent", "%", "por alvo; média simples das amostras",
        "TraCI lane", "collect_lane_details")
    add("phase_N_seconds", "s", "por alvo/fase", "TraCI trafficlight")
    for label in TRIP_FIELDS.values():
        unit = "m" if "meters" in label else "contagem" if label == "stops" else "s"
        add(" ".join(f"{stat}_{label}" for stat in ("mean", 'p50', 'p90', "p95", 'p99', "std", "min", "max", "median")),
            unit, "viagens concluídas; nulo se não há chegada", "tripinfo")
    add("co2_grams fuel_grams co_grams hc_grams nox_grams pmx_grams", "g", "veículos ativos no horizonte",
        "TraCI vehicle; depende do modelo de emissão", "collect_emissions")
    add("electricity_wh", "Wh", "veículos ativos no horizonte", "TraCI vehicle", "collect_emissions")
    add("teleports_started collision_vehicles", "eventos/veículos (não únicos)", "episódio",
        "TraCI simulation", "collect_events")
    add("cpu_seconds", "s CPU", "Python e filhos; amostrado", "psutil", "collect_resources")
    add("peak_rss_mb", "MiB", "Python e filhos; pico amostrado", "psutil", "collect_resources")
    add("reward", "adimensional", "episódio de avaliação", "soma das recompensas")
    add("actions.csv", "s / índice / escolha", "ações por alvo/fase", "registro TraCI", "collect_actions")
    from .metricas_ampliadas import EXTENDED
    registered = {row['métrica'] for row in rows}
    for name, (_, _, unit, flag) in EXTENDED.items():
        if name not in registered:
            add(name, unit, 'janela medida; rede, faixa, movimento ou classe conforme a tabela', 'TraCI / detectores E1-E2 / integração temporal', flag)
    return rows


def training_workload(config):
    algorithm = get_algorithm(config.get("algorithm", "PPO"))
    constructor = algorithm.constructor_parameters(config)
    total = int(config.get(algorithm.config_key, {}).get("total_timesteps", 2048))
    if algorithm.name != "PPO":
        return {"passos solicitados": total}
    steps = constructor["n_steps"]
    batch = constructor["batch_size"]
    epochs = constructor["n_epochs"]
    if steps < 2 or batch < 2 or batch > steps or steps % batch:
        raise ValueError("Use n_steps e batch_size >= 2, batch_size <= n_steps e n_steps múltiplo do minibatch")
    rollouts = math.ceil(total / steps)
    return {"épocas por coleta": epochs, "coletas completas previstas": rollouts,
            "passos efetivos previstos": rollouts * steps,
            "minibatches por época": steps // batch,
            "atualizações de gradiente previstas": rollouts * epochs * (steps // batch),
            "episódios completos previstos": math.floor(rollouts * steps /
                math.ceil(float(config["duration_seconds"]) / float(config.get("control", config.get("ppo", {})).get("decision_seconds", 5))))}


def export_catalogs(output, config):
    output = Path(output)
    version, options = sumo_options()
    for name, rows in {"sumo_options": options, "effective_parameters": parameter_rows(config),
                       "metrics_catalog": metric_rows(config), "traci_queries": traci_getters()}.items():
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    (output / "catalog_scope.json").write_text(json.dumps({
        "sumo_version": version, "sumo_cli_options": len(options),
        "scope": "Todas as opções CLI do SUMO instalado e consultas get públicas dos domínios TraCI. "
                 "Atributos internos de redes, vType, modelos e ferramentas como netconvert não são opções CLI SUMO. "
                 "Valores do template não substituem os valores efetivos registrados em run_config.json.",
        "training_workload": training_workload(config),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
