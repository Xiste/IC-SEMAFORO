# 3. Parâmetros usados na simulação

Esta página acompanha **uma execução com a configuração atual**. Os valores vêm de [`config/cenario.json`](../config/cenario.json) e do código do pipeline. A [referência detalhada](referencia_parametros.md) registra todos os campos, argumentos e chamadas para consulta técnica.

## Em uma linha

O pipeline gera tráfego de teste, roda o SUMO por **600 segundos**, mede veículos parados e viagens não concluídas, e usa essa pontuação para comparar durações de semáforo. Ele roda sem abrir `sumo-gui`.

## 1. Escolher o cenário

| Pergunta | Valor usado agora | Onde alterar |
| --- | --- | --- |
| Qual mapa? | Rede de Uberlândia em `dados/rede/` | `network` |
| Por quanto tempo? | **600 s**, passo de **1 s** | `duration_seconds`, `step_seconds` |
| Quantos veículos? | **360 veículos/h** de teste, sem contagens reais por via | `demand` |
| Como repetir o mesmo teste? | Semente **11** | `seeds` |
| Qual sinal muda? | `FAM_RONDON_PARANA`, fases **0–5** | `targets` |
| Qual plano da planilha é consultado? | Plano **4**, somente como referência | `plans`, `plan_id` |

## 2. Gerar veículos

A interface usa volumes definidos para o experimento, informados como total da rede ou veículos/h por entrada, com saídas automáticas. Esses cenários são registrados com `demand.synthetic: true`. As medições de veículos/h da Settran estão sendo aguardadas; os volumes de teste não devem ser apresentados como tráfego real calibrado.

Importação, calibração de contagens e distribuição por cruzamento foram retiradas da tela de configuração. O suporte no pipeline e os arquivos de execuções anteriores continuam preservados. Quando as medições chegarem, será necessário conferir período, sentido e seção de contagem e associar cada registro ao trecho correspondente da rede. Contagens de passagem em cruzamentos consecutivos não devem gerar novamente os mesmos veículos em cada entrada.

O modo atual é `demand.mode: "random"`. [`demanda.py`](../semaforos/cenario/demanda.py) transforma **360 veículos/h** em uma partida a cada **10 s** (`3600 ÷ 360`) e chama `randomTrips.py`. Ele recebe a rede, os tempos **0–600 s**, a semente **11** e grava `trips.trips.xml` e `routes.rou.xml`.

O pipeline também aceita `observed_counts` para ajustar rotas às contagens de passagem e `flows` quando as origens e os destinos são conhecidos. Uma contagem de veículos/h por via não identifica, sozinha, os destinos dessas viagens.

## 3. Rodar o SUMO

[`execucao.py`](../semaforos/simulacao/execucao.py) passa **dez opções** ao executável no fluxo de tempos fixos:

| Grupo | Opções e valores atuais |
| --- | --- |
| Entradas | `--net-file` = mapa; `--route-files` = rotas geradas |
| Relógio e repetição | `--begin 0`, `--end 600`, `--step-length 1`, `--seed 11` |
| Arquivos de resultado | `--tripinfo-output`, `--summary-output`, `--statistic-output` — cada um na pasta da execução |
| Mensagens | `--no-step-log true` |

`traci.start()` acrescenta a porta `--remote-port`, escolhida para controlar a execução. O pipeline define **12 opções** entre as 462 do catálogo local; as outras **450** seguem os padrões da instalação. Veja o [item 2](configuracoes_sumo.md) e a [referência detalhada](referencia_parametros.md).

## 4. Aplicar um candidato e medir

O programa original do semáforo tem seis fases: **verde 41 s → amarelo 3 s → totalmente vermelho 1 s**, repetidas para o outro movimento. O piloto só altera os verdes; estados, ordem, amarelos e limpezas não mudam.

A cada passo de 1 s, TraCI conta os veículos parados nas faixas controladas e os veículos que entraram ou chegaram. A pontuação é:

```text
veículo-segundos parados nas faixas controladas
+ 120 × veículos ativos ou aguardando inserção ao fim
```

**Menor pontuação é melhor para essa medida.** Por exemplo, numa execução-base já verificada, foram **150 veículo-segundos parados** e **12 viagens não concluídas**: `150 + 120 × 12 = 1590`. Os valores de cada execução ficam em `metrics.json`. Se nenhum semáforo for selecionado, o código usa uma medida global de veículos parados em vez das faixas controladas.

## 5. Repetir no treinamento

| Ajuste | Valor atual | Papel |
| --- | ---: | --- |
| Tentativas (`iterations`) | 20 | Número de configurações medidas pelo SUMO. |
| Início aleatório (`warmup_random`) | 10 | Primeira é a base; as próximas nove são sorteadas. |
| Candidatos avaliados pela MLP (`candidate_pool`) | 100 | A MLP escolhe um para medir no SUMO em cada tentativa posterior. |
| Verde mínimo | 8 s | Também limitado pela faixa de 60% a 140% do original. |
| Amarelo mínimo | 3 s | Nunca menor que o amarelo original. |
| Totalmente vermelho mínimo | 1 s | Nunca menor que o intervalo original. |
| Penalidade por viagem não concluída | 120 s | Entra na fórmula da pontuação. |

Para este semáforo, o piloto testa **24–58 s de verde** nos índices 0 e 3; amarelos de 3 s e limpezas de 1 s ficam fixos. A rede neural pequena (MLP) tem camadas **2 → 32 → 16 → 1** e ajuda a escolher configurações para testar. **A pontuação gravada sempre vem do SUMO.** Os detalhes do ajuste estão na [referência detalhada](referencia_parametros.md).

## Rodar e encontrar os arquivos

Na pasta `SistemaDeSemaforos`:

```powershell
python pipeline.py run
python pipeline.py train
```

Cada comando cria uma pasta em `resultados/`. `run` grava `summary.json` e as saídas de cada semente; `train` grava `dataset.jsonl`, `best_candidate.json`, `surrogate_model.pt` e subpastas por tentativa. O [guia de treinamento](treinamento.md) mostra como reaplicar o melhor candidato.

**Limite atual:** a rede SUMO modela esse cruzamento com duas fases verdes e ciclo de 90 s, enquanto o plano 4 da planilha descreve quatro estágios e ciclo de 110 s. Os veículos também são sintéticos. O resultado descreve o experimento atual, ainda não uma programação validada para a rua.
