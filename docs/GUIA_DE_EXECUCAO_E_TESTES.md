# Comandos de teste e execução

Guia operacional: preparar, executar, conferir e reproduzir. Todos os comandos
partem da raiz do repositório. Visão geral: [README](../README.md).

## Preparação

Requisitos: Python 3.10+, `make`, SUMO com `randomTrips.py` e `duarouter`.
Ambiente auditado: **SUMO 1.27.1**. Não há pacote Python adicional exigido pelo
código de produção. Para GUI, são necessários `sumo-gui` e uma sessão gráfica.

```bash
export SUMO_HOME=/usr/share/sumo
sumo --version
```

`sumo` e `duarouter` devem estar no `PATH`. Ao trocar de versão, confira o
[catálogo de configurações](configuration_catalog.csv) e revalide
as opções de observação.

## Testar o código

```bash
PYTHONDONTWRITEBYTECODE=1 make test
```

Executa testes de geração, execução, agregação e persistência. Eles simulam os
processos externos; não produzem episódios SUMO reais. A variável impede
caches Python durante esse comando.

## Gerar somente demanda

```bash
make demand-random
make demand-random DEMAND_ARGS='--duration 60 --period 5'
```

Produz `random.trips.xml` e `random.rou.xml` em `SistemaDeSemaforos/demandas/`,
sem simular. Uma nova geração no mesmo destino substitui os arquivos anteriores
após validar os novos. Fluxo: [Funcionamento — demanda](GUIA_DE_FUNCIONAMENTO.md#2-demanda-random).

Opções do gerador independente:

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--duration` | `7200` | Janela de partidas, em segundos. |
| `--period` | `1.5` | Intervalo entre partidas, em segundos. |
| `--net-file` | Rede Rondon Norte | Rede para gerar e rotear. |
| `--output-dir` | `SistemaDeSemaforos/demandas/` | Destino do par de arquivos. |
| `--seed` | Sorteada | Repete o sorteio conhecido, com mesmas rede e ferramentas. |

## Executar episódios

```bash
make run-random
make run-random RUN_ARGS='--episodes 10'
make run-random RUN_ARGS='--episodes 3 --gui'
```

Cada episódio sorteia uma seed, gera demanda, aguarda o SUMO e consolida seus
dados. O próximo só começa depois. O terminal informa sua pasta exclusiva em
`outputs/outputs-random/`; resultados anteriores não são substituídos.

O perfil padrão `core` prioriza indicadores consolidados. Para observações
detalhadas adicionais:

```bash
make run-random RUN_ARGS='--metrics-profile full'
```

Perfis, resultados e desempenho medido: [Funcionamento](GUIA_DE_FUNCIONAMENTO.md).

## Verificação rápida com SUMO real

Dois episódios com seis solicitações cada, até esgotar a demanda:

```bash
make run-random RUN_ARGS='--episodes 2 --duration 30 --period 5'
```

Execução limitada a 60 segundos simulados, que pode deixar viagens incompletas:

```bash
make run-random RUN_ARGS='--duration 30 --period 5 --end 60'
```

Acrescente `--gui` se necessário. Sem `--end`, o SUMO encerra naturalmente ao
esgotar a demanda. Esses comandos reais geram dados; remova verificações
descartáveis só depois de conferir se não são evidências necessárias.

## Todas as opções do runner

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--episodes` | `1` | Quantidade de episódios sequenciais independentes. |
| `--gui` | Desativado | Abre e fecha a interface em cada episódio. |
| `--duration` | `7200` | Janela de partidas da demanda, em segundos. |
| `--period` | `1.5` | Intervalo entre partidas, em segundos. |
| `--end` | Sem limite explícito | Limita o tempo simulado; pode truncar viagens. |
| `--net-file` | Rede Rondon Norte | Rede de entrada; identifica um baseline compartilhado. |
| `--output-dir` | `outputs/outputs-random/` | Subpasta dentro desse diretório para organizar resultados. |
| `--metrics-profile` | `core` | Seleciona observações `core` ou `full`; não altera demanda/controladores. |

```bash
python3 -m SistemaDeSemaforos.simulation.episode_runner --help
make run-random RUN_ARGS='--output-dir outputs/outputs-random/verificacao --duration 30 --period 5'
```

Essas são as opções do projeto, não todas as opções SUMO. O catálogo completo
das superfícies auditadas está em
[configuration_catalog.csv](configuration_catalog.csv).

## Conferir uma execução

Abra `metrics.json`: a lista `metrics` começa pelos resultados principais,
com `label_pt`, `description_pt`, `value` e `unit`. Quando há viagens concluídas,
perda média de tempo e espera média aparecem primeiro, seguidas da vazão de
chegadas e do número de veículos concluídos. `priority` indica a camada de
leitura; `kind` distingue resultados, contexto e diagnóstico.

Confira também `status`, `trip_records_unfinished`, `trip_records_undeparted`,
`teleports` e `collisions` quando presentes; métricas favoráveis precisam ser
interpretadas junto da integridade do episódio. `seed`, `simulation_seed`,
`vehicles_generated` e `execution_time_seconds` permanecem na mesma lista.
`manifest.json` identifica baseline, argumentos reais, controladores e observações
habilitadas. A classificação não retira informação nem modifica os valores.

Para scripts, indexe por `metric_name` e leia `data_type`/`value`, tolerando campos
adicionais; não dependa da posição de um registro. Novos resumos usam
`schema_version: 2`; entidades continuam no schema 1 e manifestos no schema 2.
Arquivos antigos são preservados. Estrutura, unidades, prioridades e limites de
interpretação: [Funcionamento — consolidados](GUIA_DE_FUNCIONAMENTO.md#formato-dos-consolidados).

Falhas interrompem o lote e preservam os arquivos disponíveis. Consulte `error`,
`generation.log` e `sumo.log`. Avisos de congestionamento podem indicar
teletransportes; não significam por si só erro no gerador. A limitação de avisos
repetidos no log não altera a regra SUMO de teletransporte.

## Reproduzir uma execução

1. Preserve a pasta do episódio **e** o baseline indicado por
   `manifest.json.baseline`. O baseline inclui rede, defaults, versão e código
   identificados por hash. Ferramentas externas precisam continuar disponíveis
   na versão registrada.
2. Para repetir a dinâmica com a demanda exata, reutilize
   `inputs/random.rou.xml` e `network.net.xml` do baseline. Os argumentos
   efetivamente usados estão em `manifest.json.simulation.command`;
   `inputs/sumo_config.sumocfg` guarda opções explícitas.
3. Ao reaproveitar os argumentos/configuração, troque **todos os destinos de
   saída**, inclusive os caminhos no arquivo adicional de observação. Caminhos
   preservados podem ser absolutos. Não execute a configuração histórica sem
   adaptá-los, pois isso pode sobrescrever os dados originais.
4. Para refazer também a geração, use a seed e os parâmetros registrados com a
   mesma rede e ferramentas. Exemplo, substituindo os valores:

```bash
make demand-random DEMAND_ARGS='--seed 123 --duration 7200 --period 1.5 --net-file outputs/baselines/ID/network.net.xml --output-dir SistemaDeSemaforos/demandas/reproducao'
```

O runner de episódios sorteia seeds; não possui uma opção CLI de replay.
Reprodução não se resume a executar novamente `make run-random`.

## Reauditar catálogos e custo

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_configuration_catalog.py --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_metrics_catalog.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_metrics_catalog.py --episodes outputs/outputs-random
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_observation_pipeline.py --repetitions 2
```

O benchmark gera uma única demanda de 400 viagens e compara observação mínima,
core e full duas vezes, em ordem invertida. Preserva evidências em
`outputs/benchmarks/`, com seed e tempos. `--seed` permite repetir o caso;
esse argumento pertence ao benchmark/gerador, não ao CLI do runner.

Para atualizar configurações após mudar a instalação, execute
`scripts/audit_configuration_catalog.py --probe-defaults` e revise o CSV. Esse probe
usa TraCI em t=0 apenas para auditoria. A opção `--refresh-descriptions` consulta
documentação oficial versionada e exige rede. Não são tarefas por episódio.

## Arquivos gerados e limpeza

Use [Funcionamento — resultados](GUIA_DE_FUNCIONAMENTO.md#5-resultados-e-por-que-são-separados)
para identificar o papel de cada output.
Caches/temporários são regeneráveis; episódios e baselines referenciados são
evidências. Não exclua um baseline enquanto algum episódio preservado depender
dele. Os CSVs das planilhas antigas estão em `docs/auditoria_historica.zip`; basta abrir
o ZIP e consultar `LEIA_ME.txt`. Eles não descrevem o estado atual.

Os dados das validações anteriores foram removidos por solicitação do responsável.
A próxima execução recria apenas suas próprias pastas. `tests/` contém código de
teste e deve permanecer; não é saída gerada.
