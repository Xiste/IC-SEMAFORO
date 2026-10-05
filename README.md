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

## Direção estratégica

Estado atual: execução SUMO com demanda aleatória, programas semafóricos do mapa,
observação, métricas e rastreabilidade. Ainda não há treinamento de modelos,
perfil calibrado com fluxos reais ou controlador adaptativo implementado.
O trabalho em desenvolvimento está concentrado na consolidação da etapa 1,
incluindo a organização e interpretação dos resultados.

1. **Etapa atual, em consolidação:** estabelecer um sistema confiável de execução,
   simulação e treinamento, com pipeline explicável, reproduzível, organizado e
   operacionalmente eficiente. Treinamento é parte da direção, não capacidade atual.
2. **Planejado:** criar perfis de execução e demanda para os dados reais da Rondon
   Norte, com planos semafóricos, fluxos disponíveis e futuros metadados de fluxo.
3. **Planejado:** ampliar controle e estimação, incluindo os algoritmos derivados
   de Hazarika e, futuramente, a reconstrução/estimação da rede baseada em Acciai,
   com treinamento, validação e comprovação experimental. Hazarika será uma
   estratégia de controle distinta do SUMO nativo e dos demais controladores.
4. **Planejado:** treinar e evoluir modelos progressivamente, incorporando novos
   dados, metadados, cenários e possibilidades de execução.
5. **Planejado:** consolidar dados experimentais para que a equipe de dashboards
   e apresentação produza evidências claras, rastreáveis e defensáveis dos métodos.

As etapas 2 a 5 orientam decisões de organização; não são funcionalidades
implementadas. A revisão de `metrics.json` pertence à etapa 1 e preserva os
cálculos e o conjunto CORE existente.

## Onde encontrar cada coisa

| Local | Responsabilidade |
| --- | --- |
| `SistemaDeSemaforos/network/` | Rede-base de Rondon Norte, comum aos perfis semafóricos. |
| `SistemaDeSemaforos/demand/` | Gerar viagens e calcular rotas com ferramentas SUMO. |
| `SistemaDeSemaforos/simulation/` | Coordenar episódios e preservar o cenário utilizado. |
| `SistemaDeSemaforos/metrics/` | Solicitar observações, agregá-las e gravar resultados. É código, não uma pasta de dados. |
| `docs/` | Guias, catálogos, auditoria SETTRAN, histórico e diretrizes internas, agrupados por função. |
| `scripts/` | Conferir catálogos e comparar desempenho; não faz parte da execução cotidiana. |
| `tests/` | Testes automatizados do código; não são resultados descartáveis. |
| `outputs/` | Dados gerados, criados somente ao executar. Não entram no Git. |

Dentro de `outputs/`, **`outputs-random/` guarda episódios** e **`baselines/`
guarda o cenário compartilhado por eles**. Esse compartilhamento evita copiar
mapa, código e configurações fixas em cada episódio. `benchmarks/` só aparece
quando se executa a comparação de desempenho, não com `make run-random`.

Dentro de `docs/`, cada pasta tem uma função única: `guias/` contém instruções
humanas; `catalogos/` contém tabelas consultáveis de configuração e métricas;
`settran/` contém a auditoria e a normalização dos dados semafóricos reais;
`historico/` guarda o ZIP legado; e `interno/` contém diretrizes de colaboração.
Os catálogos e o artefato SETTRAN são dados de auditoria, não arquivos carregados
durante uma execução `current`.

`current` continua padrão. A seleção SETTRAN para teste de plano fixo está
preparada, mas sua execução ainda depende de movimentos e transições comprovados.
Não há agenda nem troca automática de planos. Veja os [comandos](docs/guias/GUIA_DE_EXECUCAO_E_TESTES.md).

## Documentação

Leia apenas o documento necessário para sua tarefa:

- [Comandos](docs/guias/GUIA_DE_EXECUCAO_E_TESTES.md): preparar o ambiente, executar, testar e reproduzir.
- [Funcionamento](docs/guias/GUIA_DE_FUNCIONAMENTO.md): mapa, demanda, APIs, configurações e resultados, na ordem do pipeline.
- [Configurações](docs/catalogos/configuration_catalog.csv) e [métricas](docs/catalogos/metrics_catalog.csv): consultas detalhadas por campo; não são leitura introdutória.
- [Auditoria SETTRAN](docs/settran/settran_audit.csv): normalização dos planos reais e lacunas que ainda impedem sua execução.
  A [conferência temporária dos TLS](docs/settran/current_tls_audit.csv) resume a infraestrutura atual, incluindo sinais sem plano SETTRAN conhecido.
- [Relatório incremental](RELATORIO_INCREMENTAL.md): decisões e verificações históricas. Entradas antigas podem ter sido substituídas pelas mais recentes.

As regras de colaboração estão em [DIRETRIZES_COLABORACAO_IA.txt](docs/interno/DIRETRIZES_COLABORACAO_IA.txt).
Os dados de teste anteriores foram removidos a pedido do responsável. O guia de
funcionamento preserva o resumo das medições; o relatório registra os detalhes.
