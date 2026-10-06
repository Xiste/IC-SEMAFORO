# Arquitetura proposta e estado de implementação

## Entendimento e limites atuais

O objetivo é controlar **nove cruzamentos de Rondon Norte** em SUMO, comparando
um agente PPO com planos validados, sob a mesma demanda e sementes de avaliação.
O inventário local do SUMO 1.27.1 encontrou nove cruzamentos na planilha, 28
`tlLogic` e zero `route`, `vehicle` ou `flow` no XML da rede. Só o ID nominal
`FAM_RONDON_PARANA` pode ser associado diretamente a um nome da planilha.
Essa associação ainda não valida seus movimentos: o programa da rede tem
dois verdes e ciclo de 90 s, enquanto o plano 4 da planilha tem quatro
estágios e ciclo de 110 s. Os outros oito IDs, links e estágios aguardam
conferência espacial e operacional. O comando `inspect` apresenta os índices
dos links e as fases, sem fazer correspondências por aproximação.

O comando antigo `train` é **um piloto de busca de tempos por modelo substituto**,
não é PPO. O novo comando `ppo-train` e a interface executam um PPO dinâmico
no mesmo sinal nominal; veja [o guia executável](ppo_interface.md). A referência
ainda é o programa da rede, sem reproduzir o plano da planilha. Apenas os verdes
0 e 3 do sinal nominal estão selecionados; amarelo
e vermelho de limpeza mantêm as durações da rede. Os demais 27 sinais seguem
seus programas originais durante o piloto. Nenhum resultado atual permite
inferir ganho para os nove cruzamentos ou para o tráfego real.

As dependências de SUMO, Gymnasium, PPO e Streamlit estão em
`requirements.txt`. `matplotlib` pode ser acrescentado quando os gráficos
comparativos forem implementados.
O modo `edge_volumes` já permite informar veículos/h por via; destinos não
informados são gerados como saídas alcançáveis sintéticas. Os nomes dessas
vias não constam no XML, então a interface usa seus IDs SUMO.

## Sequência para chegar ao PPO

1. Conferir os nove pares nome–ID, links de entrada e saída, movimentos,
   pedestres, sequência de estágios e tempos mínimos obrigatórios. Registrar
   diferenças planilha–rede; não ajustar a planilha automaticamente.
2. Definir cenários de demanda com taxa em veículos/hora, pares origem–destino
   conectados, janelas temporais, tipos de veículo, duração e semente. No modo
   origem–destino, proporções de conversão são opcionais; não são exigidas se
   os pares já determinarem o destino. Baixa, média, alta e variável serão
   rótulos de cenários **sintéticos** até existir medição real.
3. Medir uma referência de rede e, depois da reconciliação, uma referência de
   planilha. Registrar veículos previstos, inseridos, concluídos, ativos e
   aguardando inserção, além de `tripinfo` inclusive para viagens incompletas.
4. Criar `gymnasium.Env` com um único agente centralizado para os nove sinais.
   Cada observação conterá, por aproximação controlada, filas por faixa,
   quantidade de veículos, velocidades ou ocupação disponíveis por TraCI,
   fase vigente, tempo transcorrido e tempo até a próxima troca. Não incluir
   demanda futura ou tempo final da viagem em observações. Validar com
   `stable_baselines3.common.env_checker.check_env`.
5. Começar com ação por cruzamento que escolha uma extensão discreta do verde
   atual ou a transição para o próximo estágio permitido. O supervisor aplica
   duração mínima/máxima do verde, sequência verde→amarelo→limpeza, intervalos
   fixos de segurança e máximo sem atendimento. Ações simultâneas dos nove
   sinais são avaliadas no mesmo instante de decisão, sem saltar transições.
   A compatibilidade dos movimentos e pedestres deve ser validada no mapa
   antes de habilitar o agente. Ciclo e vermelho de cada movimento resultam
   da sequência; defasagem é parâmetro de coordenação, não tempo vermelho
   independente. Amarelo e limpeza só poderão ser adaptados após validação
   específica de segurança.
6. Treinar `PPO("MlpPolicy", env)` com redes de política e valor MLP de duas
   camadas de 64 unidades cada como ponto de partida. Configurar
   `n_epochs=10`, `n_steps`, `batch_size`, `total_timesteps`, duração do episódio
   e sementes separadamente. Dez épocas são passadas de atualização sobre
   cada lote; não representam dez episódios nem garantem convergência.
   Normalizar observações usando estatísticas do treino e congelá-las na
   avaliação. Cada conjunto de pesos de objetivos gera um treinamento novo.
7. Avaliar em sementes e demandas não usadas para seleção do modelo,
   repetindo referência, PPO e, se útil, controlador simples. Comparar médias,
   dispersão, veículos incompletos e métricas por cruzamento e rede. A
   coordenação pode ser medida por tempos de viagem em corredores e paradas
   sucessivas, sempre sob as mesmas condições.

## Objetivos e mensuração

Uma recompensa inicial por intervalo de decisão é

`r_t = -(w_e E_t/S_e + w_f F_t/S_f + w_v V_t/S_v + w_p P_t/S_p)`.

Os pesos não negativos `w_e`, `w_f`, `w_v` são prioridades configuradas e
normalizadas para soma 1. `E_t` é a espera incremental em veículo-segundos,
`F_t` a área sob a fila em veículo-segundos e `V_t` uma aproximação do atraso
de viagem corrente, em veículo-segundos, comparando progresso com tempo de
percurso livre. `P_t` penaliza veículos que não entraram ou não concluíram;
`w_p` é restrição experimental fixa. As escalas `S_*` são estimadas apenas
em episódios de referência do conjunto de treino, salvas com o modelo e
mantidas constantes na avaliação. Tempo completo de viagem é medido na
chegada pelo `tripinfo`, usado no relatório e, se desejado, como termo tardio
de recompensa sem atribuir ao agente informação futura. Acumulados TraCI
não devem ser somados repetidamente; o incremento é medido por passo ou
por diferença controlada.

O passo SUMO inicial é 1 s. O intervalo de decisão, por exemplo 5 s, depende
da validação dos mínimos. O episódio inicia com rede e demanda reiniciadas
na semente definida e termina no horizonte simulado, com contagem explícita
dos veículos restantes. `terminated` representa fim natural do cenário e
`truncated` um limite externo. Um agente centralizado vê a rede conjunta e
coordena ações, mas seu espaço de ações cresce com nove sinais e pode ter
crédito de recompensa difícil; ele **não é** uma implementação multiagente.

## Interface e execução

Uma interface Python separada do SUMO usa Streamlit para formulário,
inspeção, progresso, comparação e exportação, com processos de trabalho
independentes por experimento. O processo cria pasta UUID, valida entradas,
gera rotas, inicia `sumo` sem janela via TraCI, registra logs e resultados e
fecha a conexão em `finally`; `sumo-gui` é opção de inspeção. Iniciar treino,
avaliar um modelo salvo e executar inferência são operações distintas.
Cancelamento deve sinalizar o processo de trabalho, fechar TraCI e registrar
execução interrompida. O piloto da interface implementa configuração,
treinamento PPO, avaliação contra o programa da rede, progresso, cancelamento
e exportação CSV; as demais capacidades seguem na sequência acima.

O catálogo de opções do executável local está em `catalogo_completo_sumo.md`.
Ele cobre opções de linha de comando do SUMO 1.27.1; não cobre todos os
atributos XML, chamadas TraCI, nem parâmetros do algoritmo. As métricas
essenciais iniciais são espera incremental, fila, viagens concluídas,
incompletas, partidas, chegadas e uso de tempo real/simulado. Velocidade,
ocupação, emissões e eventos podem ser habilitados por cenário após medir
o custo de coleta. Para cada métrica exportada, registrar origem, unidade,
frequência, agregação e limites no manifesto do experimento.

Fontes: [TraCI Python](https://sumo.dlr.de/docs/TraCI/Interfacing_TraCI_from_Python.html),
[semáforos SUMO](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html),
[tripinfo e viagens incompletas](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html),
[ambiente Gymnasium no SB3](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html).
