# Simulação de tráfego — Rondon Norte

Gera demanda aleatória, executa SUMO e grava métricas de tráfego em arquivos.
Uma rede física atende aos perfis semafóricos `current` e
`settran`; os planos SETTRAN reais continuam bloqueados por dados operacionais
ausentes. `current` e métricas `core` são os padrões.

Instale Python 3.10+, `make` e SUMO com `randomTrips.py` e `duarouter`.
Com os executáveis no `PATH` e `SUMO_HOME` apontando para a instalação:

```bash
export SUMO_HOME=/usr/share/sumo
make run-random
make run-random RUN_ARGS='--episodes 10'
make run-random RUN_ARGS='--metrics-profile full'
make test
```

Cada execução cria um lote em `outputs/outputs-random/`; cada episódio tem
`metrics.json` com resultados, seeds e dados da execução. Não há relatório no
terminal. O perfil `full` também conserva observações brutas e detalhes por
entidade. Entradas temporárias são removidas após sucesso; resultados ficam
fora do Git.

O [guia de funcionamento](docs/GUIA_DE_FUNCIONAMENTO.md) reúne preparação,
execução, SETTRAN, resultados e validação. Para apresentar ao professor, use
[CONFIGURACOES.csv](docs/CONFIGURACOES.csv) e
[METRICAS.csv](docs/METRICAS.csv), com 65 itens selecionados em cada arquivo. As
[diretrizes de colaboração](docs/DIRETRIZES_COLABORACAO_IA.txt)
orientam a manutenção.
