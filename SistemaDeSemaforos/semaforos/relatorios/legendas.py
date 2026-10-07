"""Nomes e explicações em português, preservando os identificadores técnicos."""

import re


# Nome legível, significado, unidade.
METRICS = {
    "intersection": ("Cruzamento", "Nome do cruzamento associado ao controlador SUMO; métricas continuam discriminadas por controlador.", "nome"),
    "edge_id": ("Trecho medido", "ID SUMO do trecho onde o detector virtual conta passagens.", "ID"),
    "measured_vehicles_per_hour": ("Fluxo informado", "Contagem por hora fornecida pelo usuário para calibração.", "veículos/h"),
    "fitted_vehicles_per_hour": ("Fluxo ajustado nas rotas", "Passagens previstas pela combinação de rotas sintéticas antes da simulação.", "veículos/h"),
    "passed_vehicles": ("Veículos que passaram", "Veículos distintos detectados durante o episódio, somando as faixas do trecho.", "veículos"),
    "realized_vehicles_per_hour": ("Fluxo realizado", "Passagens detectadas divididas pelo horizonte, convertidas para uma hora; pode diferir devido a congestionamento e início da simulação.", "veículos/h"),
    "planned_vehicles": ("Veículos planejados", "Viagens previstas na demanda; fluxos podem ter contagem estimada.", "veículos"),
    "planned_vehicles_estimated": ("Contagem planejada estimada", "Indica se a quantidade planejada foi estimada a partir de fluxos.", "sim/não"),
    "departed": ("Veículos inseridos", "Veículos que efetivamente entraram na simulação.", "veículos"),
    "arrived": ("Veículos que chegaram", "Veículos que concluíram a viagem dentro do horizonte.", "veículos"),
    "unfinished": ("Viagens em andamento", "Veículos que partiram e ainda não chegaram ao fim do episódio.", "veículos"),
    "pending_departure": ("Partidas pendentes", "Veículos ainda aguardando inserção ao fim do episódio.", "veículos"),
    "tripinfo_completed": ("Viagens concluídas no relatório", "Registros tripinfo com chegada válida; base das estatísticas de viagem.", "viagens"),
    "tripinfo_unfinished": ("Viagens incompletas no relatório", "Registros tripinfo sem chegada; excluídos das médias e percentis de viagem.", "viagens"),
    "simulated_seconds": ("Tempo simulado", "Tempo transcorrido no relógio do SUMO.", "s"),
    "real_seconds": ("Tempo real de execução", "Duração medida pelo relógio do computador.", "s"),
    "wait_vehicle_seconds": ("Espera acumulada na rede", "Soma dos incrementos de espera dos veículos ativos por passo. Não é a média de espera por viagem.", "veículo·s"),
    "queue_vehicle_seconds": ("Fila acumulada nos alvos", "Veículos parados nas entradas controladas multiplicados pelo tempo; faixas compartilhadas podem duplicar contagens.", "veículo·s"),
    "active_vehicle_seconds": ("Tempo acumulado de veículos ativos", "Quantidade de veículos ativos multiplicada pelo tempo. Aproxima a permanência no horizonte observado.", "veículo·s"),
    "global_halted_vehicle_seconds": ("Paradas acumuladas na rede inteira", "Veículos com velocidade inferior a 0,1 m/s multiplicados pelo passo, em toda a rede.", "veículo·s"),
    "global_peak_halted_vehicles": ("Pico de parados na rede inteira", "Maior quantidade simultânea de veículos com velocidade inferior a 0,1 m/s.", "veículos"),
    "peak_halted_vehicles": ("Pico de fila do controlador", "Maior quantidade simultânea de veículos parados nas entradas desse controlador.", "veículos"),
    "mean_lane_speed_meters_per_second": ("Velocidade média nas faixas", "Média simples das amostras válidas de velocidade por faixa e passo; não é ponderada pelo número de veículos.", "m/s"),
    "mean_lane_occupancy_percent": ("Ocupação média das faixas", "Média simples da ocupação das faixas amostradas nas entradas do controlador.", "%"),
    "phase_N_seconds": ("Tempo na fase N", "Tempo observado na fase indicada por N durante o episódio.", "s"),
    "co2_grams": ("Emissão de CO₂", "Taxas de dióxido de carbono integradas no horizonte; depende do modelo de emissão.", "g"),
    "co_grams": ("Emissão de CO", "Taxas de monóxido de carbono integradas no horizonte.", "g"),
    "hc_grams": ("Emissão de hidrocarbonetos", "Taxas de hidrocarbonetos integradas no horizonte.", "g"),
    "nox_grams": ("Emissão de óxidos de nitrogênio", "Taxas de NOx integradas no horizonte.", "g"),
    "pmx_grams": ("Emissão de partículas", "Taxas de material particulado integradas no horizonte.", "g"),
    "fuel_grams": ("Consumo de combustível", "Taxas de consumo integradas no horizonte, conforme modelo SUMO.", "g"),
    "electricity_wh": ("Consumo elétrico positivo", "Taxas positivas de consumo elétrico integradas; valores negativos de regeneração não são descontados.", "Wh"),
    "teleports_started": ("Teletransportes iniciados", "Eventos de retirada temporária de veículos pelo SUMO; examine o motivo no log.", "eventos"),
    "collision_vehicles": ("Participações em colisões", "Soma das contagens de veículos em colisão por passo; não representa veículos únicos nem número de colisões.", "participações"),
    "cpu_seconds": ("Tempo de CPU", "Tempo de processamento amostrado do Python e processos filhos; pode diferir do tempo real.", "s CPU"),
    "peak_rss_mb": ("Pico de memória amostrado", "Maior memória residente observada do Python e filhos. Não garante capturar o pico absoluto.", "MiB"),
    "reward": ("Recompensa acumulada", "Soma das recompensas do episódio. Depende dos pesos, escalas e penalidade por viagens pendentes.", "adimensional"),
    "actions.csv": ("Histórico de ações", "Arquivo com escolhas PPO e durações aplicadas por controlador e fase.", "arquivo"),
    "controller": ("Controlador avaliado", "Algoritmo treinado, programa de referência da rede ou heurística reativa de filas.", "identificador"),
    "seed": ("Semente aleatória", "Identificador da geração aleatória; comparações usam a mesma demanda por semente.", "inteiro"),
    "tls_id": ("ID do controlador SUMO", "Identificador do controlador na rede; um cruzamento pode ter vários IDs.", "identificador"),
    "episode": ("Episódio", "Número sequencial de uma execução do SUMO no treinamento.", "inteiro"),
    "timesteps": ("Passos de treinamento", "Quantidade de decisões do agente já coletadas; não equivale a segundos SUMO.", "passos"),
    "episode_output": ("Pasta do episódio", "Local dos arquivos de demanda, tripinfo e ações desse episódio.", "caminho"),
    "TimeLimit.truncated": ("Episódio truncado", "Indica encerramento por truncamento informado pelo ambiente vetorizado.", "sim/não"),
    "time_seconds": ("Instante da ação", "Momento no relógio SUMO em que a ação foi registrada.", "s"),
    "phase_index": ("Índice da fase", "Posição da fase no programa SUMO, começando em zero.", "inteiro"),
    "phase_kind": ("Tipo da fase", "Verde, amarelo ou vermelho de limpeza.", "categoria"),
    "action": ("Escolha do agente", "Escolha 0/1/2: mínima/original/máxima em phase_durations; no modo antigo, encurtar/manter/estender verde.", "índice"),
    "phase_elapsed_seconds": ("Tempo decorrido na fase", "Tempo já cumprido pela fase no instante registrado.", "s"),
    "phase_started_seconds": ("Início da fase", "Instante de início estimado pelo tempo decorrido fornecido pelo TraCI.", "s"),
    "remaining_seconds_before_action": ("Tempo restante antes da ação", "Tempo previsto até a troca de fase antes da intervenção.", "s"),
    "selected_total_duration_seconds": ("Duração total escolhida", "Duração mínima, original ou máxima selecionada para a fase.", "s"),
    "applied_phase_duration_seconds": ("Tempo restante aplicado", "Tempo restante enviado ao TraCI; não é necessariamente a duração total da fase.", "s"),
}

TRIPS = {
    "travel_time_seconds": ("tempo de viagem", "Duração da viagem após a partida.", "s"),
    "trip_waiting_seconds": ("espera por viagem", "Espera registrada no tripinfo da viagem concluída.", "s"),
    "time_loss_seconds": ("tempo perdido", "Atraso associado à circulação abaixo da velocidade ideal, segundo o SUMO.", "s"),
    "stops": ("paradas por viagem", "Quantidade de episódios de espera registrada no tripinfo.", "paradas"),
    "route_length_meters": ("distância percorrida", "Comprimento percorrido na viagem concluída.", "m"),
    "departure_delay_seconds": ("atraso na partida", "Diferença entre partida prevista e inserção efetiva.", "s"),
}
STATS = {"mean": "Média", "p95": "Percentil 95", "std": "Desvio padrão",
         "min": "Mínimo", "max": "Máximo", "median": "Mediana"}


def metric_legend(name):
    if name in METRICS:
        return METRICS[name]
    if re.fullmatch(r"phase_\d+_seconds", name):
        return (f"Tempo na fase {name.split('_')[1]}", METRICS["phase_N_seconds"][1], "s")
    for statistic, title in STATS.items():
        if name.startswith(statistic + "_") and name[len(statistic) + 1:] in TRIPS:
            label, description, unit = TRIPS[name[len(statistic) + 1:]]
            statistic_help = {"p95": "Valor abaixo do qual ficam 95% das observações.",
                              "std": "Desvio padrão populacional das viagens concluídas.",
                              "median": "Valor central das observações."}.get(statistic, "")
            return f"{title} de {label}", f"{description} Apenas viagens concluídas; vazio quando não há chegada. {statistic_help}".strip(), unit
    for suffix, title in (("_mean", "Média entre execuções"), ("_std", "Desvio entre execuções"), ("_count", "Execuções com valor")):
        if name.endswith(suffix):
            label, description, unit = metric_legend(name[:-len(suffix)])
            extra = " Desvio padrão amostral; vazio com uma única execução." if suffix == "_std" else ""
            return f"{title}: {label}", description + extra, "execuções" if suffix == "_count" else unit
    return name, "Campo técnico presente neste resultado; consulte o relatório da execução para sua definição.", ""


def metric_column_label(name):
    label, _, unit = metric_legend(name)
    return f"{label} [{unit}]" if unit else label


def metric_legend_rows(columns):
    return [{"código técnico": name, "nome em português": metric_legend(name)[0],
             "unidade": metric_legend(name)[2], "legenda em português": metric_legend(name)[1]}
            for name in columns]


def portuguese_metric_table(table):
    # O código entre parênteses mantém as colunas identificáveis e únicas.
    return table.rename(columns={name: f"{metric_column_label(name)} ({name})" for name in table.columns})


PARAMETERS = {
    "algorithm": ("Algoritmo de aprendizado", "Nome do algoritmo registrado para construir, treinar e carregar a política; padrão PPO."),
    "network": ("Rede SUMO", "Arquivo .net.xml com vias, faixas, conexões e programas semafóricos."),
    "plans": ("Planilha de planos", "Fonte dos tempos reais para auditoria; não substitui automaticamente os programas da rede."),
    "mapping_path": ("Mapeamento dos cruzamentos", "Arquivo que associa cruzamentos e controladores e registra a conferência operacional."),
    "plan_id": ("Identificador do plano", "Plano selecionado na planilha; seu número não indica horário de ativação."),
    "duration_seconds": ("Duração do episódio", "Horizonte de uma execução do SUMO, em segundos simulados."),
    "step_seconds": ("Passo do SUMO", "Avanço do relógio e frequência da coleta TraCI, em segundos."),
    "seeds": ("Sementes do treino", "O PPO atual usa a primeira semente para inicialização; episódios seguintes recebem sementes geradas pelo ambiente."),
    "evaluation.seeds": ("Sementes de avaliação", "Sementes diferentes da inicial do treino para comparar controladores nas mesmas demandas."),
    "collect_lane_details": ("Coletar detalhes das faixas", "Ativa médias de velocidade e ocupação das entradas dos alvos."),
    "collect_emissions": ("Coletar emissões e consumo", "Ativa CO₂, CO, HC, NOx, partículas, combustível e eletricidade; aumenta consultas TraCI."),
    "collect_events": ("Coletar eventos", "Registra teletransportes iniciados e participações de veículos em colisões."),
    "collect_resources": ("Coletar CPU e memória", "Registra tempo de CPU e pico amostrado de memória do Python e filhos."),
    "collect_actions": ("Registrar ações", "Salva escolhas e tempos aplicados no arquivo actions.csv."),
    "objectives.waiting": ("Peso da espera", "Importância da espera dos veículos ativos na recompensa; os pesos são normalizados pela soma."),
    "objectives.queues": ("Peso das filas", "Importância das filas nas entradas dos alvos na recompensa."),
    "objectives.travel": ("Peso do tempo em trânsito", "Importância da aproximação por veículos ativos × tempo; não usa diretamente a média final de viagem."),
    "decision_seconds": ("Intervalo de decisão", "Tempo simulado entre decisões PPO; deve ser pelo menos o passo SUMO."),
    "n_epochs": ("Épocas por coleta", "Número de passagens de otimização pelos dados de cada coleta. Não é o número de simulações."),
    "n_steps": ("Passos por coleta", "Decisões coletadas antes de atualizar o modelo; no piloto, múltiplo do minibatch."),
    "batch_size": ("Tamanho do minibatch", "Quantidade de amostras usada em cada atualização de gradiente; pelo menos 2."),
    "total_timesteps": ("Orçamento do treinamento", "Total solicitado de decisões PPO; a execução pode arredondar para completar a última coleta."),
    "action_mode": ("Modo de controle", "phase_durations escolhe durações das fases; green_extension ajusta somente verdes."),
    "phase_types": ("Tipos de fase ajustáveis", "green = verde; yellow = amarelo; all_red = vermelho de limpeza."),
    "phase_indices": ("Índices dos verdes controlados", "Posições das fases verdes selecionadas no programa SUMO, começando em zero."),
    "tls_id": ("ID do controlador", "Identificador do semáforo/controlador na rede SUMO."),
    "name": ("Nome do cruzamento", "Nome usado para associar o alvo aos arquivos do projeto."),
    "mode": ("Modelo de demanda", "random = taxa total sintética; flows = pares origem–destino; edge_volumes = novas viagens por trecho; observed_counts = ajuste de rotas a contagens internas."),
    "vehicles_per_hour": ("Volume de tráfego", "Taxa em veículos/h. O total planejado depende da duração do episódio."),
    "flows": ("Fluxos origem–destino", "Lista de entradas, saídas e taxas por par de vias."),
    "edge_volumes": ("Volumes por via", "Taxas por trecho SUMO: geração de novas viagens ou contagens internas conforme o modelo de demanda escolhido."),
    "calibration_tolerance": ("Tolerância do ajuste", "Erro relativo máximo entre contagem informada e fluxo das rotas ajustadas; não garante o mesmo fluxo realizado sob congestionamento."),
    "maximum_cycle_seconds": ("Máximo de ciclo permitido", "Limita a soma dos maiores tempos permitidos de todas as fases de cada controlador."),
    "from_edge": ("Via de entrada", "ID da aresta SUMO onde as viagens são inseridas."),
    "to_edge": ("Via de destino", "ID da aresta de saída; se vazio no modo por via, uma saída alcançável é sorteada."),
    "destinations": ("Proporções dos destinos", "Destinos por origem; shares devem somar 1."),
    "share": ("Proporção", "Fração do total atribuída ao destino ou tipo de veículo."),
    "time_profile": ("Perfil temporal", "Janelas contíguas que distribuem o volume ao longo do episódio."),
    "begin": ("Início da janela", "Instante inicial da janela em segundos simulados."),
    "end": ("Fim da janela", "Instante final da janela em segundos simulados."),
    "multiplier": ("Multiplicador temporal", "Peso da janela na distribuição do volume; não altera sozinho o total planejado."),
    "vehicle_types": ("Tipos de veículos", "Classes e proporções de veículos usadas na geração da demanda."),
    "vClass": ("Classe SUMO", "Classe de circulação que determina as permissões de acesso às vias."),
    "id": ("Identificador", "Identificador do elemento na definição da demanda."),
    "iterations": ("Iterações da busca legada", "Usado pela busca anterior; não controla o treinamento PPO."),
    "warmup_random": ("Amostras iniciais da busca legada", "Exploração aleatória da busca anterior; não usada no PPO."),
    "candidate_pool": ("Candidatos da busca legada", "Quantidade de candidatos da busca anterior; não usada no PPO."),
    "minimum_green_seconds": ("Verde mínimo", "Limite inferior usado ao derivar as opções de duração dos verdes, em segundos."),
    "minimum_yellow_seconds": ("Amarelo mínimo", "Mínimo experimental em segundos; o modo atual também preserva o tempo original da fase."),
    "minimum_all_red_seconds": ("Limpeza mínima", "Mínimo experimental de vermelho de limpeza, em segundos; preserva o tempo original."),
    "unfinished_penalty_seconds": ("Penalidade por viagens pendentes", "Coeficiente em segundos convertido pela escala da recompensa para penalizar viagens incompletas e partidas pendentes."),
    "gui": ("Exibir SUMO-GUI", "Abre o simulador gráfico durante treino/avaliação; pode aumentar o tempo real."),
    "policy": ("Política PPO", "Modelo de política; MlpPolicy usa uma rede neural para escolher ações."),
    "env": ("Ambiente de aprendizado", "Ambiente Gymnasium que conecta decisões PPO ao SUMO por TraCI."),
    "learning_rate": ("Taxa de aprendizado", "Tamanho do passo do otimizador ao ajustar os pesos da rede neural."),
    "gamma": ("Desconto das recompensas futuras", "Controla a importância das recompensas futuras em relação às imediatas."),
    "gae_lambda": ("Coeficiente de vantagem", "Controla o cálculo da vantagem pelo método GAE, equilibrando variância e viés."),
    "clip_range": ("Limite de atualização da política", "Faixa de recorte PPO para limitar mudanças grandes na política."),
    "clip_range_vf": ("Recorte da função de valor", "Limite opcional de atualização da estimativa de valor; None desativa esse recorte."),
    "normalize_advantage": ("Normalizar vantagens", "Padroniza as vantagens antes das atualizações PPO."),
    "ent_coef": ("Peso da exploração", "Coeficiente da entropia na perda; influencia a diversidade das ações."),
    "vf_coef": ("Peso da função de valor", "Coeficiente da perda da rede que estima o retorno futuro."),
    "max_grad_norm": ("Norma máxima do gradiente", "Limita a magnitude dos gradientes durante a otimização."),
    "use_sde": ("Exploração dependente do estado", "Opção SB3 para espaços de ação compatíveis; desabilitada no piloto com ações discretas."),
    "sde_sample_freq": ("Frequência de amostragem SDE", "Frequência de renovação do ruído quando SDE está ativo; sem efeito no piloto atual."),
    "rollout_buffer_class": ("Classe de armazenamento da coleta", "Implementação do buffer de experiências; None seleciona o padrão SB3."),
    "rollout_buffer_kwargs": ("Parâmetros do armazenamento", "Argumentos adicionais do buffer de experiências."),
    "target_kl": ("Limite de divergência da política", "Limite opcional que pode interromper épocas antecipadamente; None desativa."),
    "stats_window_size": ("Janela de estatísticas", "Quantidade de episódios usados nas estatísticas móveis da SB3."),
    "tensorboard_log": ("Pasta de registros TensorBoard", "Destino opcional de registros; None significa desabilitado."),
    "policy_kwargs": ("Arquitetura da política", "Configuração das redes de política e valor; no piloto, duas camadas de 64 neurônios em cada rede."),
    "verbose": ("Detalhamento dos registros", "Nível de mensagens emitidas pela SB3."),
    "seed": ("Semente aleatória", "Inicializa os geradores aleatórios; a semente SUMO efetiva é registrada por episódio."),
    "device": ("Dispositivo de processamento", "CPU/GPU; auto permite que a SB3 escolha o dispositivo disponível."),
    "_init_setup_model": ("Inicialização do modelo", "Opção interna SB3 para criar redes e otimizadores no construtor."),
    "action_spec": ("Opções de ação por fase", "Lista de controladores, tipos, índices e durações mínima/original/máxima disponíveis ao agente."),
    "tripinfo-output.write-unfinished": ("Registrar viagens incompletas", "Inclui no tripinfo os veículos sem chegada ao encerrar o SUMO."),
    "no-step-log": ("Ocultar registros por passo", "Desativa a impressão de uma mensagem a cada passo SUMO."),
    "step-length": ("Passo de integração SUMO", "Avanço do relógio SUMO por passo, em segundos."),
    "net-file": ("Arquivo da rede", "Arquivo .net.xml carregado pelo SUMO."),
    "route-files": ("Arquivo de demanda", "Rotas/viagens geradas para cada episódio."),
    "tripinfo-output": ("Arquivo de viagens", "Arquivo XML com duração, espera, distância e demais atributos por viagem."),
}


def parameter_legend(name):
    normalized = re.sub(r"\[\d+\]", "", name)
    if name.startswith("TLS."):
        return "Fase do programa SUMO", "Duração original em segundos e estados dos links, na ordem de índices do programa."
    if name.startswith("SUMO.command."):
        normalized = name[len("SUMO.command."):]
    if "maximum_seconds" in name or "minimum_seconds" in name:
        kind = "amarelo" if ".yellow." in name else "limpeza" if ".all_red." in name else "fase"
        return f"Duração {'máxima' if 'maximum' in name else 'mínima'}: {kind}", "Limite experimental em segundos para as escolhas do agente; deve incluir a duração original e respeitar os mínimos."
    if "phase_duration_bounds" in name:
        return "Limites por fase", "Objeto ID:índice com durações mínima e máxima específicas, em segundos."
    if normalized in PARAMETERS:
        return PARAMETERS[normalized]
    key = normalized.split(".")[-1]
    return PARAMETERS.get(key, (name, "Parâmetro técnico do cenário; consulte a definição do arquivo de configuração."))


SUMO_CATEGORIES = {
    "configuration": "Arquivos de configuração", "input": "Arquivos de entrada",
    "output": "Arquivos e métricas de saída", "time": "Tempo da simulação",
    "processing": "Processamento e comportamento da simulação", "routing": "Cálculo de rotas",
    "report": "Registros, avisos e erros", "emissions": "Modelos de emissões",
    "communication": "Comunicação entre veículos", "battery": "Baterias e energia",
    "example_device": "Dispositivo de exemplo", "ssm_device": "Indicadores de conflito e segurança",
    "toc_device": "Transição do controle do veículo", "driver_state_device": "Estado do motorista",
    "bluelight_device": "Veículos de emergência", "fcd_device": "Dados de posição e movimento",
    "elechybrid_device": "Veículos elétricos híbridos", "taxi_device": "Operação de táxis",
    "glosa_device": "Recomendação de velocidade para semáforos", "tripinfo_device": "Informações das viagens",
    "vehroutes_device": "Registro das rotas percorridas", "friction_device": "Atrito da pista",
    "fcd_replay_device": "Reprodução de trajetórias", "traci_server": "Servidor TraCI",
    "mesoscopic": "Simulação mesoscópica", "random_number": "Geração aleatória",
    "gui_only": "Interface gráfica SUMO",
}
