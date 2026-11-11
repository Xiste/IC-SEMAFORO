# Controle adaptativo por condições das entradas

A interface configura `control.action_mode=adaptive_signals` nos novos treinamentos. O modelo recebe condições das faixas de entrada e escolhe qual abertura compatível atender em cada controlador, a cada intervalo de decisão. Ele pode manter o verde atual ou solicitar outro verde cadastrado, sem seguir obrigatoriamente a ordem do programa inicial.

## Informações usadas

O SUMO fornece sensores virtuais, organizados por controlador e faixa, em ordem estável. Cada faixa fornece seis variáveis normalizadas: presença, número de participantes, fila, velocidade, ocupação e ocupação máxima das saídas conectadas. Para acessos de pedestres, presença, contagem, espera e velocidade vêm das pessoas na rede; a ocupação é aproximada pela capacidade e o componente de ocupação a jusante é zero. Permanecem também os seis indicadores agregados por controlador, incluindo estado e tempo do sinal.

`sensor_layout` registra os IDs das faixas, arestas, conexões atendidas e saídas. Esse contrato identifica o que uma integração futura precisará medir e associar. **Não há conexão com câmeras ou detectores físicos nesta implementação.** Não há visão computacional nem detecção de objetos em vídeos. As observações vêm do estado simulado, sem ruído, falhas de comunicação ou oclusões; isso precisa ser considerado ao avaliar a transferência para equipamentos reais.

## Decisões e transições

Uma ação escolhe um dos verdes compatíveis de cada controlador. A associação entre verde e movimentos é mantida internamente, mas a interface não exige escolher uma “etapa”: a tabela mostra as entradas atendidas, o verde mínimo e o verde máximo, filtrados por cruzamento.

O controle exige programas com trios verde/amarelo/todos vermelhos. A solicitação de outra abertura só é executada depois do verde mínimo. A transição passa pelo amarelo e pela limpeza do verde que está terminando, preservando integralmente suas durações cadastradas; somente depois entra o verde solicitado. Solicitações novas durante a transição não interrompem essa limpeza. Nenhum movimento simultâneo novo é criado pelo modelo. O máximo de verde é imposto mesmo que o modelo peça para continuar; quando necessário, outra abertura é escolhida pela maior duração sem atendimento. Há também uma intervenção de atendimento após 120 s sem abertura. Esse valor é um gatilho, não uma garantia de espera máxima: mínimos e transições ainda precisam ser cumpridos.

O mecanismo usa `setPhase` e `setPhaseDuration` conforme o [controle TraCI documentado pelo SUMO](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html#controlling_traffic_lights_via_traci). Ele preserva as restrições da rede experimental; não constitui certificação operacional para uso em via pública.

## Treinamento e comparação

O PPO aprende a escolher as aberturas a partir dessas observações. As durações resultam das decisões sucessivas e dos limites, em vez de escolher antecipadamente um tempo para cada fase de um ciclo. A função de recompensa existente foi preservada para não misturar a mudança de controle com uma mudança de objetivo.

A referência da rede continua executando seus tempos originais, sem intervenção adaptativa. O controle por filas usa as filas das aberturas candidatas, sujeito à mesma proteção de transições do modelo. As comparações mantêm demanda e sementes pareadas.

Modelos antigos permanecem preservados e podem ser usados com seus cenários originais. **É necessário treinar um modelo novo para este modo**, pois mudaram as observações e o espaço de ações. O manifesto registra `action_mode`, `action_spec`, `observation_version=lane_sensors_v1` e `sensor_layout`; a avaliação recusa alterações incompatíveis. Cenários CLI antigos mantêm o comportamento anterior até que o modo seja alterado explicitamente. Preparar a rede ainda cria o programa de referência e seus grupos compatíveis; a interface aplica o modo adaptativo ao configurar a execução.

Testes curtos de treino/salvamento/carregamento verificam integração, sem demonstrar convergência, redução de filas ou desempenho com câmeras reais. A etapa seguinte da pesquisa é calibrar a demanda, treinar com orçamento adequado e comparar treinamentos independentes nas sementes reservadas.
