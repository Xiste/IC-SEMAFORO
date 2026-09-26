# Simulação de tráfego — Rondon Norte

O projeto gera viagens aleatórias, executa episódios no SUMO e consolida métricas.
Usa a rede **Rondon Norte**, confirmada pelo responsável pelo projeto. Os semáforos
seguem os programas estáticos do mapa; ainda não há controle adaptativo.

```text
mapa → gerar viagens e rotas → executar SUMO → consolidar resultados
```

Para executar, com o SUMO instalado:

```bash
make run-random                            # um episódio
make run-random RUN_ARGS='--episodes 3'     # três episódios sequenciais
make run-random RUN_ARGS='--gui'            # com interface gráfica
```

Cada episódio recebe uma demanda nova. O padrão solicita 4.800 viagens:
7.200 segundos de partidas, uma a cada 1,5 segundo. Tempo simulado é diferente
do tempo que o computador leva para executar.

## Onde encontrar cada coisa

| Local | Responsabilidade |
| --- | --- |
| `SistemaDeSemaforos/network/` | Mapa original de Rondon Norte. |
| `SistemaDeSemaforos/demand/` | Gerar viagens e calcular rotas com ferramentas SUMO. |
| `SistemaDeSemaforos/simulation/` | Coordenar episódios e preservar o cenário utilizado. |
| `SistemaDeSemaforos/metrics/` | Solicitar observações, agregá-las e gravar resultados. É código, não uma pasta de dados. |
| `docs/` | Guias, dois catálogos de consulta e diretrizes. |
| `scripts/` | Conferir catálogos e comparar desempenho; não faz parte da execução cotidiana. |
| `tests/` | Testes automatizados do código; não são resultados descartáveis. |
| `outputs/` | Dados gerados, criados somente ao executar. Não entram no Git. |

Dentro de `outputs/`, **`outputs-random/` guarda episódios** e **`baselines/`
guarda o cenário compartilhado por eles**. Esse compartilhamento evita copiar
mapa, código e configurações fixas em cada episódio. `benchmarks/` só aparece
quando se executa a comparação de desempenho, não com `make run-random`.

## Documentação

Leia apenas o documento necessário para sua tarefa:

- [Comandos](docs/COMANDOS_TESTE.md): preparar o ambiente, executar, testar e reproduzir.
- [Funcionamento](docs/FUNCIONAMENTO.md): mapa, demanda, APIs, configurações e resultados, na ordem do pipeline.
- [Configurações](docs/configuration_catalog.csv) e [métricas](docs/metrics_catalog.csv): consultas detalhadas por campo; não são leitura introdutória.
- [Relatório incremental](RELATORIO_INCREMENTAL.md): decisões e verificações históricas. Entradas antigas podem ter sido substituídas pelas mais recentes.

As regras de colaboração estão em [diretrizesIA.txt](docs/diretrizesIA.txt).
Os dados de teste anteriores foram removidos a pedido do responsável. O guia de
funcionamento preserva o resumo das medições; o relatório registra os detalhes.
