# PPO e interface gráfica: piloto executável

## Preparação e execução

Na pasta `SistemaDeSemaforos`, com SUMO 1.27.1 disponível no `PATH` ou em
`SUMO_HOME`:

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run interface.py
```

Sem interface:

```powershell
.\.venv\Scripts\python.exe pipeline.py ppo-train
.\.venv\Scripts\python.exe pipeline.py ppo-eval --model resultados/PASTA/ppo_model.zip
```

`ppo-train` salva `manifest.json`, `progress.json`, `summary.json`, episódios
isolados e `ppo_model.zip`. `ppo-eval` grava `runs.csv` e `summary.json`, com
uma execução do programa original da rede e outra da política PPO para cada
semente. A interface inicia esses comandos em um processo separado, mostra
logs e tempo real e permite solicitar cancelamento. O comando `train` antigo
continua sendo a busca por modelo substituto; não é PPO.

## Controle implementado

O ambiente `SemaforosEnv` usa `gymnasium.Env`; `reset` gera demanda e inicia
SUMO, `step` aplica a ação por TraCI e avança a simulação, e `close` encerra
a conexão. O agente é **centralizado**: uma observação reúne os sinais em
`targets` e `MultiDiscrete([3] × N)` contém uma ação por sinal. Neste momento,
`N=1`, pois só `FAM_RONDON_PARANA` está associado nominalmente. Os outros
semáforos mantêm seus programas da rede.

Por sinal, a observação vetorial contém seis valores escalados para `[0,1]`:
fila aproximada de veículos parados nas faixas controladas, número de
veículos nelas, velocidade média, índice da fase, tempo na fase e tempo até
a troca. A observação vem do estado TraCI atual, sem conhecimento da demanda
futura. Escalas de 20 veículos/faixa, 20 m/s e 60 s são escolhas explícitas
do piloto, não calibração de tráfego real.

Durante um verde selecionado, a ação `0` solicita encerramento após o mínimo,
`1` mantém o programa e `2` estende o verde em um intervalo de decisão, sem
exceder o máximo. Em amarelo e vermelho de limpeza, a ação é ignorada. A
transição é executada pelo programa SUMO existente, sem mudar estado de link,
ordem de fase, amarelo ou limpeza. O mínimo e máximo atuais dos verdes são
24–58 s. O passo SUMO é 1 s e a decisão ocorre a cada 5 s por padrão.
O ciclo e o vermelho dos movimentos resultam dessas fases; não são ações
independentes. Esta é uma **restrição de software no piloto**, não certificação
dos tempos para operação na rua. Compatibilidade de movimentos, pedestres e
máximo sem atendimento precisam ser validados antes de habilitar nove sinais.

A recompensa do piloto por intervalo é o negativo da média ponderada de
`espera_incremental/60`, `fila_em_veículo-segundos/60` e
`veículos_ativos×segundos/600`. O último termo é uma **aproximação** de tempo
de viagem em curso; tempo completo de viagem consta em `tripinfo.xml` quando
o veículo chega. Pesos de espera, fila e viagem são configurados na interface
e registrados no manifesto. O episódio termina após `duration_seconds`; a
recompensa final penaliza veículos ativos e aguardando inserção. Esses
denominadores fixos são provisórios. Para análise comparável, será preciso
calibrá-los nos episódios de referência do conjunto de treino e congelá-los
na avaliação.

O PPO usa `MlpPolicy` com redes de política e valor `[64, 64]`. Os campos
`n_epochs=10`, `n_steps=128`, `batch_size=64` e `total_timesteps=2048` são
independentes. Dez épocas significam dez passadas de atualização por lote,
não dez episódios. A duração do episódio é outro campo. Cada alteração dos
pesos é um novo experimento de treino. O arquivo de modelo salvo é usado na
avaliação determinística, com a mesma demanda e sementes para a referência.

## Limitações e próxima validação

O piloto não prova melhoria de desempenho. A planilha e o programa
`FAM_RONDON_PARANA` divergem: quatro estágios e 110 s contra dois verdes e
90 s. A referência da comparação é o **programa da rede**, ainda não o plano
da planilha. O modelo só pode ser estendido aos nove após conferir
nome–ID–link–estágio, movimentos, pedestres e limites operacionais. Os modos
de demanda atuais são taxa sintética total pela rede, volume por via e fluxos
por par de vias. No modo por via, a interface pré-lista as entradas do sinal
nominal e aceita outras vias da rede. O volume em veículos/h gera
`arredondar(volume × duração/3600)` viagens por entrada, espaçadas no tempo.
Uma saída opcional pode ser informada por via; quando vazia, o gerador sorteia
entre as saídas alcançáveis por automóveis e registra a escolha como
**sintética** em `demand_manifest.json`. O SUMO roteia os `<trip>` gerados.
Contagens de entrada não fornecem proporções de conversão medidas, e partidas
efetivas podem atrasar sob congestionamento. Tipos de veículo, perfil
temporal, proporções de conversão, relatórios amplos e demanda medida ainda
precisam ser implementados. Não use o piloto para configurar sinais reais.

Fontes: [TraCI Python](https://sumo.dlr.de/docs/TraCI/Interfacing_TraCI_from_Python.html),
[controle de semáforos](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html),
[ambientes personalizados no SB3](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html),
[PPO no SB3](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html).

## Atualização de outubro de 2026

O modo por via agora aceita `time_profile`, `vehicle_types` e `destinations` proporcionais, inclusive na interface. A avaliação usa `evaluation.seeds` separadas da semente de treino e gera `signals.csv`, `aggregate.csv`, `comparison.png` e `report.md` além de `runs.csv` e `summary.json`. Veja [mapeamento e demanda](mapeamento_e_demanda.md) e [catálogo de métricas](catalogo_metricas.md). As afirmações anteriores nesta página de que essas opções ainda precisam ser implementadas estão superadas.
