# Comandos de teste e execução

## O que é

Este arquivo reúne os comandos usados para verificar o código, gerar uma
demanda random e executar episódios no SUMO.

Execute todos os comandos na raiz do repositório.

## Organização dos arquivos

| Pasta | Responsabilidade |
| --- | --- |
| `docs/` | Diretrizes, instruções de uso e auditorias. |
| `SistemaDeSemaforos/demand/` | Geração da demanda random. |
| `SistemaDeSemaforos/simulation/` | Execução do SUMO e dos episódios. |
| `SistemaDeSemaforos/network/` | Rede viária usada pelo projeto. |
| `SistemaDeSemaforos/demandas/` | XMLs gerados automaticamente. |
| `tests/demand/` | Testes do gerador. |
| `tests/simulation/` | Testes da execução. |

## Preparação

São necessários Python 3.10+, `make` e SUMO. Neste ambiente:

```bash
export SUMO_HOME=/usr/share/sumo
```

Para usar a interface visual, `sumo-gui` também deve estar instalado e a
sessão precisa ter acesso a um ambiente gráfico.

## Testes automatizados

```bash
make test
```

Esse comando executa separadamente os testes em `tests/demand/` e
`tests/simulation/`. Os processos externos são simulados: o teste não abre o
SUMO e não altera as demandas existentes.

## Gerar somente a demanda random

```bash
make demand-random
```

O comando escolhe uma seed, cria `random.trips.xml` e calcula
`random.rou.xml`. Ele não inicia a simulação. Consulte [DEMANDA.md](DEMANDA.md)
para entender cada arquivo e o fluxo completo.

## Executar episódios random

Um episódio sem interface visual:

```bash
make run-random
```

Três episódios sem interface visual:

```bash
make run-random RUN_ARGS='--episodes 3'
```

Três episódios com interface visual:

```bash
make run-random RUN_ARGS='--episodes 3 --gui'
```

Antes de cada episódio, uma nova demanda random é gerada. Os arquivos ficam em
`SistemaDeSemaforos/demandas/episodios/episodio_001/`,
`episodio_002/` e assim por diante. O episódio seguinte só começa quando o
anterior termina.

## Verificação rápida com SUMO real

Sem interface:

```bash
make run-random RUN_ARGS='--episodes 2 --duration 30 --period 5 --end 60'
```

Com interface:

```bash
make run-random RUN_ARGS='--episodes 2 --duration 30 --period 5 --end 60 --gui'
```

Cada episódio solicita seis viagens. `--end 60` encerra a simulação no segundo
60, mesmo que ainda existam viagens incompletas. Remova `--end 60` para deixar
o SUMO encerrar quando não houver mais veículos.

## Opções de `run-random`

| Opção | Padrão | Função |
| --- | --- | --- |
| `--episodes` | `1` | Quantidade de episódios sequenciais. |
| `--gui` | desativado | Usa `sumo-gui`; sem a opção, usa `sumo`. |
| `--duration` | `7200` | Janela de partidas da demanda de cada episódio. |
| `--period` | `1.5` | Intervalo entre partidas. |
| `--end` | sem limite | Limita o tempo de simulação e pode interromper viagens. |
| `--net-file` | rede em `SistemaDeSemaforos/network/` | Escolhe a rede SUMO. |
| `--output-dir` | `SistemaDeSemaforos/demandas/episodios` | Escolhe onde guardar as demandas dos episódios. |

Para listar as opções diretamente:

```bash
python3 -m SistemaDeSemaforos.simulation.runner --help
```

Uma falha na geração ou na simulação interrompe os episódios restantes.

## Por que aparecem avisos de teletransporte

Na reprodução de três episódios padrão, o SUMO terminou com código `0`, mas
emitiu 4.028 avisos. Eles não vieram do Makefile nem da geração dos XMLs. Foram
emitidos durante as simulações porque parte da demanda random congestionou
cruzamentos e vias locais.

Quando um veículo fica parado por 300 segundos, o SUMO pode movê-lo
temporariamente para evitar que a simulação fique bloqueada. Os motivos mais
observados foram:

- `jam`: não havia espaço na próxima via;
- `yield`: o veículo não conseguiu uma brecha em uma via prioritária;
- `wrong lane`: o veículo ficou preso em uma faixa inadequada para sua rota.

Uma ocorrência normalmente gera um aviso ao começar e outro ao terminar o
teletransporte. Por isso a quantidade de linhas é maior que a quantidade de
veículos afetados.

O runner usa `--aggregate-warnings 5`: mostra alguns exemplos de cada tipo e
depois agrupa as repetições. Essa opção só organiza os avisos do próprio SUMO.
Ela não pede arquivos estatísticos, não faz o Python ler resultados e não
calcula métricas.

Durante a investigação, foi testada temporariamente a opção
`--duration-log.statistics true`. Ela fazia o SUMO imprimir um resumo no
terminal, mas não criava uma coleta própria no projeto. Essa opção foi removida
porque a etapa atual é apenas montar a execução sistêmica.

Referência: [teletransportes no SUMO](https://sumo.dlr.de/docs/Simulation/Why_Vehicles_are_teleporting.html).
