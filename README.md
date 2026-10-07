# Simulação de tráfego — Rondon Norte

O projeto gera demanda aleatória, executa episódios no SUMO e consolida métricas
de tráfego na rede Rondon Norte, em Uberlândia.

Uma única rede física atende aos perfis semafóricos `current` e `settran`.
`current` é o padrão. A integração SETTRAN recebe planos explicitamente
selecionados, mas os dados reais atuais ainda não permitem executá-los com
segurança. A demanda permanece `random`; não há controlador adaptativo.

## Preparação

Instale Python 3.10+, `make` e SUMO com `randomTrips.py` e `duarouter`.
`sumo` e `duarouter` devem estar no `PATH`. A versão de referência é SUMO 1.27.1.

```bash
export SUMO_HOME=/usr/share/sumo
sumo --version
```

## Executar e testar

```bash
make run-random                                      # um episódio current
make run-random RUN_ARGS='--duration 30 --period 5'  # prova curta
make test
```

Resultados são criados em `outputs/outputs-random/`, com baselines compartilhados
em `outputs/baselines/`. Não entram no Git; preserve os resultados experimentais
e os baselines dos quais dependem.

O [guia de funcionamento](docs/guias/GUIA_DE_FUNCIONAMENTO.md) é a documentação
canônica: comandos, rede, demanda, SETTRAN, contrato dos dados futuros, métricas,
reprodução e validação. Ele também indica as referências técnicas detalhadas
para manutenção e leitura por IA.

As [diretrizes de colaboração](docs/interno/DIRETRIZES_COLABORACAO_IA.txt)
orientam desenvolvedores e agentes.
