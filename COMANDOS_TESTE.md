# Comandos de teste e execução

## O que é

Este arquivo reúne os comandos usados para verificar o código, gerar uma
demanda random e executar episódios no SUMO.

Execute todos os comandos na raiz do repositório.

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

Esse comando testa geração e execução com processos simulados. Ele não abre o
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
| `--net-file` | rede do projeto | Escolhe a rede SUMO. |
| `--output-dir` | `SistemaDeSemaforos/demandas/episodios` | Escolhe onde guardar as demandas dos episódios. |

Para listar as opções diretamente:

```bash
python3 -m SistemaDeSemaforos.simulation --help
```

Uma falha na geração ou na simulação interrompe os episódios restantes.
