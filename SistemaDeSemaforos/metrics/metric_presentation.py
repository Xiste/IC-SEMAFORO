"""Apresentação curta dos escalares globais, sem calcular ou modificar valores.

O catálogo de métricas continua sendo a referência técnica completa. Aqui ficam
apenas nomes humanos, unidades, populações e prioridades de leitura. Novos campos
do coletor precisam receber uma descrição explícita antes de serem publicados.
"""

import re


def _metadata(label, description, unit, priority, kind="result", category=None):
    return {
        "label_pt": label,
        "description_pt": description,
        "unit": unit,
        "kind": kind,
        "category": category or {1: "performance", 2: "operation", 3: "integrity", 4: "diagnostic"}[priority],
        "priority": priority,
    }


# Metadados permanecem na lista legada para preservar os consumidores por nome.
# A classificação permite separá-los dos resultados sem duplicar seus valores.
_CONTEXT = {
    "episode_id": ("Identificação do episódio", "Identificador único desta execução.", None),
    "episode_index": ("Posição do episódio no lote", "Número deste episódio dentro do lote solicitado.", "episódios"),
    "batch_episodes": ("Episódios solicitados no lote", "Quantidade de episódios solicitada para este lote.", "episódios"),
    "demand_model": ("Modelo de demanda", "Modelo usado para gerar as viagens deste episódio.", None),
    "seed": ("Semente da demanda", "Semente aleatória usada para reproduzir a geração da demanda.", None),
    "simulation_seed": ("Semente do SUMO", "Semente aleatória efetivamente usada pelo SUMO, distinta da semente da demanda.", None),
    "metrics_profile": ("Perfil de coleta", "Perfil core ou full que determina quais fontes de observação são coletadas.", None),
    "gui": ("Execução com interface gráfica", "Indica se a simulação foi executada com a interface gráfica do SUMO.", None),
    "started_at_utc": ("Início da execução em UTC", "Data e hora de início do episódio, no relógio civil em UTC.", None),
    "finished_at_utc": ("Fim da execução em UTC", "Data e hora de encerramento do episódio, no relógio civil em UTC.", None),
    "demand_duration_seconds": ("Janela de geração da demanda", "Duração da janela em que as partidas são solicitadas ao gerador.", "s"),
    "demand_period_seconds": ("Intervalo solicitado entre partidas", "Intervalo entre solicitações de partida no gerador de demanda.", "s"),
    "demand_first_departure_seconds": ("Primeira partida planejada", "Menor instante de partida entre os veículos das rotas geradas.", "s"),
    "demand_last_departure_seconds": ("Última partida planejada", "Maior instante de partida entre os veículos das rotas geradas.", "s"),
    "demand_departure_mean_seconds": ("Instante médio das partidas planejadas", "Média dos instantes de partida dos veículos das rotas geradas.", "s"),
    "vehicles_requested": ("Veículos solicitados ao gerador", "Quantidade prevista de solicitações pela duração e pelo intervalo de geração.", "veículos"),
    "vehicles_generated": ("Veículos com rotas geradas", "Quantidade de veículos presentes no arquivo de rotas validado.", "veículos"),
    "trips_generated": ("Viagens geradas e validadas", "Quantidade de viagens origem-destino presente no arquivo validado pelo gerador.", "viagens"),
    "simulation_begin_seconds": ("Início do tempo simulado", "Instante inicial da janela simulada, em segundos da simulação.", "s"),
    "simulation_end_seconds": ("Fim do tempo simulado", "Limite final da janela observada, incluindo o último passo de um segundo.", "s"),
    "simulation_duration_seconds": ("Duração observada da simulação", "Tempo simulado entre início e fim observados; é o denominador da vazão de viagens concluídas.", "s"),
    "simulation_end_limited": ("Limite de encerramento solicitado", "Indica se foi solicitado um instante máximo para encerrar a simulação.", None),
    "simulation_end_requested_seconds": ("Instante máximo solicitado", "Instante de encerramento solicitado ao SUMO, em tempo simulado.", "s"),
    "simulation_step_length_seconds": ("Duração do passo do SUMO", "Intervalo de tempo simulado por passo, conforme a configuração efetiva.", "s"),
    "observation_step_seconds": ("Intervalo de observação do resumo", "Intervalo entre observações do resumo usado na agregação temporal.", "s"),
}

_DIRECT = {
    "completed_throughput_vehicles_per_hour": ("Vazão de viagens concluídas", "Veículos que chegaram ao destino por hora, calculados sobre toda a duração simulada observada.", "veículos/h", 1),
    "vehicles_completed": ("Veículos que chegaram ao destino", "Total acumulado de chegadas ao destino registrado no resumo do SUMO.", "veículos", 1),
    "cumulative_insertion_delay_mean_seconds": ("Atraso médio para entrar na rede", "Última média acumulada da espera antes da inserção na rede; não é espera no trânsito.", "s", 1),
    "cumulative_removed_travel_time_mean_seconds": ("Duração média das viagens removidas", "Última média acumulada de duração dos veículos já removidos, incluindo remoções sem chegada ao destino.", "s", 2),
    "vehicles_inserted": ("Veículos inseridos na rede", "Total acumulado de veículos que efetivamente iniciaram a circulação na rede.", "veículos", 2),
    "vehicles_loaded": ("Veículos carregados pelo SUMO", "Total acumulado de veículos carregados pelo SUMO, incluindo os ainda não inseridos.", "veículos", 2),
    "vehicles_removed": ("Veículos removidos da rede", "Total acumulado de veículos retirados da rede, por chegada ou outra causa.", "veículos", 2),
    "vehicles_discarded": ("Veículos descartados na inserção", "Total de veículos descartados pelo SUMO antes de serem inseridos na rede.", "veículos", 3),
    "teleports": ("Teletransportes de veículos", "Total acumulado de teletransportes registrado pelo SUMO durante o episódio.", "eventos", 3),
    "collisions": ("Veículos envolvidos em colisões", "Contador acumulado de veículos envolvidos em colisões, conforme o resumo do SUMO.", "veículos", 3),
    "trip_records_unfinished": ("Viagens iniciadas sem chegada registrada", "Registros de viagem com partida válida e sem chegada até o encerramento, inclusive remoções com chegada negativa.", "viagens", 3),
    "trip_records_undeparted": ("Viagens registradas sem partida", "Registros de viagem sem partida; não abrangem necessariamente toda a demanda futura planejada.", "viagens", 3),
    "trip_records_vaporized": ("Viagens com remoção excepcional", "Registros com partida e chegada não negativas e motivo de remoção excepcional indicado pelo SUMO.", "viagens", 3),
    "lane_change_events": ("Mudanças de faixa", "Quantidade de eventos em que veículos passaram de uma faixa para outra.", "eventos", 2),
    "sumo_teleports_jam": ("Teletransportes por congestionamento", "Teletransportes atribuídos pelo SUMO a bloqueio por congestionamento.", "eventos", 3),
    "sumo_teleports_yield": ("Teletransportes por falta de passagem", "Teletransportes por espera excessiva para obter passagem em uma via sem prioridade.", "eventos", 3),
    "sumo_teleports_wrong_lane": ("Teletransportes por faixa incompatível", "Teletransportes de veículos presos em uma faixa sem conexão com a próxima via da rota.", "eventos", 3),
    "sumo_safety_emergency_stops": ("Paradas de emergência", "Quantidade de paradas de emergência registrada pelo SUMO.", "eventos", 3),
    "sumo_safety_emergency_braking": ("Frenagens de emergência", "Quantidade de frenagens de emergência registrada pelo SUMO.", "eventos", 3),
    "sumo_persons_loaded": ("Pessoas carregadas pelo SUMO", "Quantidade de pessoas carregadas para a simulação, quando existentes.", "pessoas", 2),
    "sumo_persons_running": ("Pessoas ainda ativas", "Quantidade de pessoas ainda ativas no encerramento da simulação.", "pessoas", 3),
    "sumo_persons_jammed": ("Pedestres com bloqueio registrado", "Contagem de pessoas que sofreram bloqueio, conforme a estatística do SUMO.", "pessoas", 3),
    "sumo_person_teleports_total": ("Teletransportes de pessoas", "Total de teletransportes de pessoas registrado pelo SUMO.", "eventos", 3),
    "sumo_person_teleports_abort_wait": ("Teletransportes por espera de transporte", "Teletransportes de pessoas por espera excessiva para embarcar.", "eventos", 3),
    "sumo_person_teleports_wrong_dest": ("Teletransportes por destino incorreto", "Teletransportes de pessoas após desembarque em destino incorreto.", "eventos", 3),
}

_TIMERS = {
    "execution": ("Tempo total de execução", "Tempo real do pipeline, incluindo coleta e inventário; exclui a escrita final de metrics.json e manifest.json."),
    "baseline_preparation": ("Tempo de preparação do baseline", "Tempo real gasto preparando ou reutilizando o baseline deste episódio."),
    "generation": ("Tempo de geração da demanda", "Tempo real gasto na geração e validação da demanda."),
    "simulation_execution": ("Tempo de execução do processo SUMO", "Tempo real gasto executando o processo SUMO com as saídas de observação habilitadas."),
    "sumo_configuration": ("Tempo de preparação da configuração SUMO", "Tempo real gasto preparando e registrando a configuração efetiva do SUMO."),
    "aggregation": ("Tempo de agregação das métricas", "Tempo real gasto consolidando as saídas nativas em métricas globais e por entidade."),
    "entity_persistence": ("Tempo de gravação das entidades", "Tempo real gasto serializando, comprimindo e gravando as métricas por entidade."),
    "file_inventory": ("Tempo de inventário dos arquivos", "Tempo real gasto inventariando arquivos e calculando tamanhos e hashes."),
}

_SOURCES = {
    "summary": "resumo temporal do SUMO", "network": "rede e suas associações",
    "trips": "viagens individuais", "statistics": "estatísticas finais do SUMO",
    "tls": "estados semafóricos", "queues": "filas por faixa",
    "lanechanges": "mudanças de faixa", "collisions": "colisões",
    "lanes": "tráfego por faixa", "edges": "tráfego por via",
    "fcd": "trajetórias individuais", "emissions": "emissões temporais",
}

# Cada conceito descreve o valor de uma observação; _aggregate explicita como
# os valores observados foram combinados e mantém amostras separadas do resultado.
_TEMPORAL = {
    "vehicles_halting": ("Veículos parados no trânsito", "número de veículos abaixo de 0,1 m/s, excluindo paradas programadas; não mede comprimento de fila", "veículos", 1),
    "vehicles_waiting_insertion": ("Veículos aguardando entrada na rede", "número de veículos cuja partida está atrasada por ainda não terem sido inseridos", "veículos", 1),
    "network_mean_speed_m_s": ("Velocidade média da rede", "velocidade média por passo, excluindo veículos em parada programada e passos sem veículos", "m/s", 2),
    "network_mean_relative_speed": ("Velocidade relativa média da rede", "velocidade relativa média ao limite permitido por passo, excluindo paradas programadas e passos sem veículos", "1", 2),
    "vehicles_running": ("Veículos em circulação", "número de veículos presentes na rede em cada passo", "veículos", 2),
    "vehicles_scheduled_stop": ("Veículos em parada programada", "número de veículos cumprindo uma parada prevista em seu plano de viagem", "veículos", 2),
    "sumo_step_computation_ms": ("Tempo de processamento por passo", "tempo real gasto pelo SUMO para processar um passo simulado", "ms", 4),
}

_TRIP = {
    "time_loss": ("Tempo perdido em relação à velocidade ideal", "tempo perdido ao circular abaixo da velocidade ideal individual, excluindo paradas programadas", "s", 1),
    "waiting_time": ("Tempo de espera no trânsito", "tempo com velocidade até 0,1 m/s, excluindo paradas programadas e espera anterior à inserção", "s", 1),
    "depart_delay": ("Atraso de partida", "tempo de espera antes da entrada efetiva do veículo na rede", "s", 1),
    "waiting_count": ("Ocorrências de espera no trânsito", "número de vezes em que o veículo passou a ter velocidade até 0,1 m/s", "eventos", 2),
    "duration": ("Duração de viagem", "tempo decorrido desde a partida até o fim do registro de viagem", "s", 2),
    "route_length": ("Distância percorrida", "distância percorrida no trecho observado da viagem", "m", 2),
    "stop_time": ("Tempo em paradas programadas", "tempo gasto cumprindo paradas previstas no plano da viagem", "s", 2),
    "depart_speed": ("Velocidade de partida", "velocidade do veículo no instante de entrada na rede", "m/s", 2),
    "arrival_speed": ("Velocidade no fim da viagem", "velocidade registrada no fim da viagem", "m/s", 2),
    "speed_factor": ("Fator individual de velocidade", "fator de velocidade desejada atribuído ao veículo pelo SUMO", "1", 2),
    "reroute_no": ("Alterações de rota", "quantidade de mudanças de rota feitas pelo veículo", "eventos", 2),
    "depart": ("Instante de partida efetiva", "instante simulado em que o veículo entrou na rede", "s", 4),
    "arrival": ("Instante registrado de chegada", "instante de chegada informado no registro de viagem", "s", 4),
    "depart_pos": ("Posição de partida na faixa", "distância desde o início da faixa até a posição de partida", "m", 4),
    "arrival_pos": ("Posição final na faixa", "distância desde o início da faixa até a posição final registrada", "m", 4),
    "depart_pos_lat": ("Posição lateral de partida", "posição lateral do veículo na faixa no instante de partida", "m", 4),
    "arrival_pos_lat": ("Posição lateral final", "posição lateral do veículo na faixa no fim do registro", "m", 4),
}

_STATUSES = {
    "completed": "viagens concluídas", "unfinished": "viagens iniciadas sem chegada registrada",
    "undeparted": "viagens registradas sem partida", "vaporized": "viagens com remoção excepcional",
}

_EMISSIONS = {
    "co2": ("Emissão de CO₂", "massa de dióxido de carbono emitida", "mg"),
    "co": ("Emissão de CO", "massa de monóxido de carbono emitida", "mg"),
    "hc": ("Emissão de hidrocarbonetos", "massa de hidrocarbonetos emitida", "mg"),
    "n_ox": ("Emissão de óxidos de nitrogênio", "massa de óxidos de nitrogênio emitida", "mg"),
    "p_mx": ("Emissão de material particulado", "massa de material particulado emitida", "mg"),
    "fuel": ("Consumo de combustível", "massa de combustível consumida", "mg"),
    "electricity": ("Consumo de energia elétrica", "energia elétrica consumida, com valores negativos indicando recuperação", "Wh"),
}

_EVENT = {
    "time": ("Instante do evento", "instante simulado em que ocorreu o evento", "s"),
    "pos": ("Posição do evento na faixa", "distância desde o início da faixa até o local do evento", "m"),
    "speed": ("Velocidade na mudança de faixa", "velocidade do veículo que mudou de faixa", "m/s"),
    "dir": ("Direção da mudança de faixa", "diferença entre índices de faixa; a média expressa o saldo de direções, não uma direção física", "1"),
    "leader_gap": ("Distância ao veículo da frente na faixa destino", "distância entre para-choques até o veículo da frente na faixa destino", "m"),
    "leader_secure_gap": ("Distância segura à frente na faixa destino", "distância necessária ao veículo da frente para respeitar as restrições de desaceleração", "m"),
    "follower_gap": ("Distância ao veículo de trás na faixa destino", "distância entre para-choques até o veículo de trás na faixa destino", "m"),
    "follower_secure_gap": ("Distância segura atrás na faixa destino", "distância necessária ao veículo de trás para respeitar as restrições de desaceleração", "m"),
    "orig_leader_gap": ("Distância à frente na faixa original", "distância entre para-choques até o veículo da frente na faixa original", "m"),
    "orig_leader_secure_gap": ("Distância segura à frente na faixa original", "distância necessária ao veículo da frente na faixa original para respeitar a desaceleração", "m"),
    "leader_speed": ("Velocidade à frente na faixa destino", "velocidade do veículo da frente na faixa destino", "m/s"),
    "follower_speed": ("Velocidade atrás na faixa destino", "velocidade do veículo de trás na faixa destino", "m/s"),
    "orig_leader_speed": ("Velocidade à frente na faixa original", "velocidade do veículo da frente na faixa original", "m/s"),
    "lat_gap": ("Distância lateral na faixa destino", "distância lateral ao vizinho mais próximo na faixa destino", "m"),
    "collider_speed": ("Velocidade do veículo que colidiu", "velocidade do agente identificado como causador da colisão pelo SUMO", "m/s"),
    "victim_speed": ("Velocidade do agente atingido", "velocidade do agente atingido na colisão", "m/s"),
}

_AGGREGATIONS = {
    "mean": ("média", "Média"), "max": ("máximo", "Maior valor"),
    "sum": ("soma", "Soma"), "min": ("mínimo", "Menor valor"),
}

_LANE_CHANGE_REASONS = {
    "strategic": "seguir a rota", "cooperative": "facilitar a passagem de outro veículo",
    "speedGain": "buscar maior velocidade", "keepRight": "manter-se à direita",
    "sublane": "ajustar a posição lateral", "traci": "atender a um comando externo TraCI",
    "urgent": "manobra urgente",
}


def _aggregate(spec, aggregation, population, *, incomplete=False, per_step=False):
    label, concept, unit, priority = spec
    # Concordância dos conceitos curtos, sem traduzir identificadores técnicos.
    preposition = "da" if concept.split()[0] in {
        "velocidade", "distância", "posição", "quantidade", "massa", "energia", "taxa",
    } else "do"
    if aggregation == "samples":
        return _metadata(f"Amostras: {label.lower()} ({population})",
                         f"Número de observações válidas {preposition} {concept}, entre {population}.",
                         "amostras", 4, "diagnostic")
    if aggregation == "excluded_samples":
        return _metadata(f"Amostras excluídas: {label.lower()}",
                         f"Observações {preposition} {concept} excluídas por valor ausente, inválido ou população vazia, quando aplicável.",
                         "amostras", 3, "diagnostic")
    suffix, operation = _AGGREGATIONS[aggregation]
    description = f"{operation} {preposition} {concept}, entre {population}."
    if incomplete:
        description += " Valores restritos ao trecho registrado."
        priority = max(priority, 3)
    kind = "diagnostic" if priority == 4 else "result"
    if per_step and aggregation == "mean":
        description = f"Média temporal {preposition} {concept}; cada passo válido tem o mesmo peso."
    return _metadata(f"{label} — {suffix} ({population})", description, unit, priority, kind)


def _statistics(name):
    """Campos opcionais do StatisticOutput habilitado pelos perfis atuais."""
    performance = {
        "clock_begin": ("Início do processo SUMO", "Instante de início do SUMO no relógio civil, em segundos desde a época Unix.", "s"),
        "clock_end": ("Fim do processo SUMO", "Instante de encerramento do SUMO no relógio civil, em segundos desde a época Unix.", "s"),
        "clock_duration": ("Tempo real interno do SUMO", "Duração real da simulação medida internamente pelo SUMO.", "s"),
        "traci_duration": ("Tempo reportado pelo SUMO para TraCI", "Tempo atribuído pelo SUMO ao campo TraCI; esse registro isolado não comprova uso de controle externo.", "s"),
        "real_time_factor": ("Fator de velocidade de execução", "Razão entre tempo simulado e tempo real de execução, conforme o SUMO.", "1"),
        "vehicle_updates_per_second": ("Atualizações de veículos por segundo real", "Taxa de processamento de atualizações de veículos registrada pelo SUMO.", "atualizações/s"),
        "person_updates_per_second": ("Atualizações de pessoas por segundo real", "Taxa de processamento de atualizações de pessoas registrada pelo SUMO.", "atualizações/s"),
    }
    if name.startswith("sumo_performance_"):
        field = name.removeprefix("sumo_performance_")
        if field in performance:
            return _metadata(*performance[field], 4, "context" if field in {"clock_begin", "clock_end"} else "diagnostic",
                             "context" if field in {"clock_begin", "clock_end"} else "diagnostic")
    populations = {
        "bike_trip_statistics": "viagens de bicicleta",
        "pedestrian_statistics": "percursos a pé",
        "ride_statistics": "etapas de transporte de pessoas",
        "transport_statistics": "etapas de transporte de contêineres",
    }
    fields = {
        "number": ("Quantidade de etapas", "Quantidade de {population} registrada pelo SUMO.", "etapas"),
        "count": ("Quantidade de viagens", "Quantidade de {population} incluída na estatística nativa do SUMO.", "viagens"),
        "route_length": ("Distância média", "Distância média das {population} registradas pelo SUMO.", "m"),
        "duration": ("Duração média", "Duração média das {population} registradas pelo SUMO.", "s"),
        "speed": ("Velocidade média", "Velocidade média das {population} registradas pelo SUMO.", "m/s"),
        "waiting_time": ("Tempo médio de espera", "Tempo médio parado por tráfego nas {population} registradas pelo SUMO.", "s"),
        "time_loss": ("Tempo médio perdido", "Tempo médio perdido ao circular abaixo da velocidade ideal nas {population}.", "s"),
        "depart_delay": ("Atraso médio de partida", "Tempo médio antes da inserção nas {population} registradas pelo SUMO.", "s"),
        "depart_delay_waiting": ("Atraso médio das partidas pendentes", "Espera média por inserção das {population} ainda sem partida.", "s"),
        "total_travel_time": ("Tempo total de viagem", "Soma das durações das {population} registradas pelo SUMO.", "s"),
        "total_depart_delay": ("Atraso total de partida", "Soma das esperas por inserção das {population} registradas pelo SUMO.", "s"),
        "bus": ("Etapas em transporte público rodoviário", "Quantidade de {population} em veículos de transporte público rodoviário.", "etapas"),
        "train": ("Etapas em transporte ferroviário", "Quantidade de {population} em veículos ferroviários.", "etapas"),
        "taxi": ("Etapas em táxi", "Quantidade de {population} em táxi.", "etapas"),
        "bike": ("Etapas em bicicleta", "Quantidade de {population} em bicicleta.", "etapas"),
        "aborted": ("Etapas não concluídas", "Quantidade de {population} que não puderam ser concluídas.", "etapas"),
    }
    for prefix, population in populations.items():
        start = f"sumo_{prefix}_"
        if name.startswith(start) and name[len(start):] in fields:
            field = name[len(start):]
            label, description, unit = fields[field]
            return _metadata(f"{label} ({population})", description.format(population=population), unit,
                             3 if field == "aborted" else 2)
    return None


def describe_metric(name: str) -> dict:
    """Retorna somente a semântica de um escalar global conhecido.

    Uma unidade ``None`` indica que unidade física não se aplica ao campo.
    O valor adimensional conhecido usa ``"1"``; não se inferem unidades pelo nome.
    """
    if name in _CONTEXT:
        return _metadata(*_CONTEXT[name], 4, "context", "context")
    if name in _DIRECT:
        return _metadata(*_DIRECT[name])
    if name in {"status", "error"}:
        label, description = {
            "status": ("Estado da execução", "Situação do pipeline: running, completed, failed ou interrupted; completed não garante a chegada de todas as viagens."),
            "error": ("Falha ou interrupção registrada", "Tipo e mensagem do erro que impediu a conclusão normal do episódio."),
        }[name]
        return _metadata(label, description, None, 3, "context", "integrity")
    if name.endswith("_time_seconds"):
        timer = name.removesuffix("_time_seconds")
        if timer in _TIMERS:
            return _metadata(*_TIMERS[timer], "s", 4, "diagnostic")
        if timer.startswith("collection_") and timer[11:] in _SOURCES:
            source = _SOURCES[timer[11:]]
            return _metadata(f"Tempo de coleta: {source}",
                             f"Tempo real gasto lendo e consolidando {source}.", "s", 4, "diagnostic")
    coverage = {
        "simulation_steps": ("Passos observados no resumo", "Quantidade de passos presentes no resumo temporal do SUMO.", "passos"),
        "queue_observation_steps": ("Passos observados de filas", "Quantidade de passos lidos na saída nativa de filas.", "passos"),
        "fcd_observation_steps": ("Passos observados de trajetórias", "Quantidade de passos lidos na saída de trajetórias individuais.", "passos"),
    }
    if name in coverage:
        return _metadata(*coverage[name], 4, "diagnostic")
    match = re.fullmatch(r"(lane|edge)_traffic_(intervals|duration_seconds|internal_included)", name)
    if match:
        source = "faixas" if match[1] == "lane" else "vias"
        specs = {
            "intervals": (f"Intervalos observados de tráfego por {source}", f"Quantidade de intervalos lidos na saída de tráfego por {source}.", "intervalos"),
            "duration_seconds": (f"Duração observada de tráfego por {source}", f"Soma das durações dos intervalos de tráfego por {source} usados na agregação.", "s"),
            "internal_included": (f"Inclusão de {source} internas", f"Indica que os resultados de tráfego por {source} também incluem conexões internas das interseções.", None),
        }
        return _metadata(*specs[match[2]], 4, "context" if match[2] == "internal_included" else "diagnostic",
                         "context" if match[2] == "internal_included" else "diagnostic")
    stats = _statistics(name)
    if stats is not None:
        return stats
    match = re.fullmatch(r"(.+?)_(excluded_samples|samples|mean|max|sum|min)", name)
    if match:
        base, aggregation = match.groups()
        if base in _TEMPORAL:
            return _aggregate(_TEMPORAL[base], aggregation, "passos observados", per_step=True)
        trip = re.fullmatch(r"(completed|unfinished|undeparted|vaporized)_trip_(.+)", base)
        if trip and trip[2] in _TRIP:
            result = _aggregate(_TRIP[trip[2]], aggregation, _STATUSES[trip[1]], incomplete=trip[1] != "completed")
            short_means = {
                "time_loss": "Tempo médio perdido", "waiting_time": "Tempo médio de espera",
                "depart_delay": "Atraso médio de partida", "duration": "Duração média de viagem",
            }
            if aggregation == "mean" and trip[2] in short_means:
                result["label_pt"] = f"{short_means[trip[2]]} ({_STATUSES[trip[1]]})"
            return result
        emission = re.fullmatch(r"(completed|unfinished|undeparted|vaporized)_emission_(.+)_abs", base)
        if emission and emission[2] in _EMISSIONS:
            label, concept, unit = _EMISSIONS[emission[2]]
            return _aggregate((label, f"{concept} por viagem", unit, 2), aggregation,
                              _STATUSES[emission[1]], incomplete=emission[1] != "completed")
        network_emission = re.fullmatch(r"network_emission_(.+)_rate", base)
        if network_emission and network_emission[1] in _EMISSIONS:
            label, concept, unit = _EMISSIONS[network_emission[1]]
            return _aggregate((f"Taxa na rede: {label.lower()}", f"taxa de {concept} por segundo, somada entre os veículos presentes",
                               f"{unit}/s", 2), aggregation, "passos observados", per_step=True)
        event = re.fullmatch(r"(lane_change|collision)_(.+)", base)
        if event and event[2] in _EVENT:
            population = "mudanças de faixa" if event[1] == "lane_change" else "colisões"
            priority = 4 if event[1] == "lane_change" or event[2] in {"time", "pos"} else 3
            return _aggregate((*_EVENT[event[2]], priority), aggregation, population)
    category = re.fullmatch(r"(lane_change|collision)_(reason|type)_([0-9a-f]*)_(value|count)", name)
    if category:
        try:
            value = bytes.fromhex(category[3]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ValueError(f"Categoria de evento inválida: {name}") from None
        population = "mudanças de faixa" if category[1] == "lane_change" else "colisões"
        attribute = "motivo" if category[2] == "reason" else (
            "tipo de veículo" if category[1] == "lane_change" else "tipo de colisão")
        if category[4] == "value":
            return _metadata(f"Categoria de {population}: {attribute}",
                             f"Identificação textual do {attribute} associado aos eventos de {population}.",
                             None, 4, "context", "context")
        meaning = value
        if category[1] == "lane_change" and category[2] == "reason":
            meaning = "; ".join(_LANE_CHANGE_REASONS.get(part, f"categoria nativa {part}")
                                for part in value.split("|"))
        return _metadata(f"{population.capitalize()}: {meaning}",
                         f"Quantidade de {population} com {attribute} “{meaning}” (registro nativo: “{value}”).",
                         "eventos", 3 if category[1] == "collision" else 4,
                         "result" if category[1] == "collision" else "diagnostic")
    raise ValueError(f"Métrica global sem apresentação cadastrada: {name}")


_HEADLINES = (
    "completed_trip_time_loss_mean", "completed_trip_waiting_time_mean",
    "completed_throughput_vehicles_per_hour", "vehicles_completed",
)

# A prioridade precede os temas; o nome serve somente como desempate estável.
_THEMES = (
    "completed_trip_time_loss_", "completed_trip_waiting_time_", "vehicles_halting_",
    "completed_trip_depart_delay_", "cumulative_insertion_delay_", "vehicles_waiting_insertion_",
    "network_mean_speed_", "network_mean_relative_speed_", "completed_trip_duration_",
    "cumulative_removed_travel_time_", "completed_trip_route_length_", "vehicles_inserted",
    "vehicles_running_", "vehicles_loaded", "vehicles_removed", "completed_trip_waiting_count_",
    "completed_trip_stop_time_", "vehicles_scheduled_stop_", "completed_trip_",
    "completed_emission_", "network_emission_", "lane_change_events", "sumo_bike_",
    "sumo_pedestrian_", "sumo_ride_", "sumo_transport_", "sumo_persons_loaded",
    "trip_records_", "unfinished_", "undeparted_", "vaporized_", "vehicles_discarded",
    "teleports", "sumo_teleports_", "collisions", "collision_", "sumo_safety_",
    "sumo_person_teleports_", "sumo_persons_", "status", "error", "lane_change_",
    "execution_time_", "simulation_execution_", "generation_time_", "baseline_preparation_",
    "sumo_configuration_", "aggregation_time_", "collection_", "entity_persistence_",
    "file_inventory_", "sumo_performance_", "sumo_step_computation_",
)


def presentation_sort_key(record: dict) -> tuple:
    """Ordena resultados, explicações, integridade e diagnóstico nessa sequência."""
    name = record["metric_name"]
    priority = describe_metric(name)["priority"]
    if name in _HEADLINES:
        return priority, _HEADLINES.index(name), 0, name
    # Quantidades de amostras e cobertura ficam depois dos diagnósticos/timers.
    if name.endswith("_samples") and not name.endswith("_excluded_samples"):
        theme = len(_THEMES) + 2
    elif name.endswith(("_intervals", "_observation_steps")) or name == "simulation_steps":
        theme = len(_THEMES) + 3
    else:
        theme = next((i for i, prefix in enumerate(_THEMES) if name.startswith(prefix)), len(_THEMES))
    suffix = name.rsplit("_", 1)[-1]
    aggregation = {"mean": 0, "max": 1, "sum": 2, "min": 3, "samples": 4}.get(suffix, 0)
    return priority, len(_HEADLINES) + theme, aggregation, name
