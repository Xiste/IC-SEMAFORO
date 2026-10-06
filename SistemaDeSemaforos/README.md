# Pipeline SUMO: Rondon Norte

**Integração da rede corrigida:** a `main` agora inclui a rede corrigida, a auditoria
dos 17 IDs candidatos para os nove cruzamentos e as contagens locais dos detectores
5 e 6. Use `config/cenario_rede_corrigida.json` ou escolha a rede na interface.
O comando `pipeline.py measurements` resume as contagens sem presumir que seus
detectores correspondam a vias SUMO. Veja [rede corrigida e medições](docs/rede_corrigida_e_medicoes.md).
O [mapeamento](docs/mapeamento_e_demanda.md) agora aceita vários controladores
por cruzamento; `targets_from_mapping` só os ativa após validar os nove.
Os programas da planilha e os pedestres ainda exigem validação operacional;
o cenário padrão permanece na rede original.

**Atualização do PPO:** a implementação inclui auditoria dos nove nomes,
demanda por via com perfil temporal, destinos proporcionais e tipos de veículo,
avaliação em sementes separadas e relatórios detalhados. Consulte
[mapeamento e demanda](docs/mapeamento_e_demanda.md),
[catálogo de métricas](docs/catalogo_metricas.md),
[pesquisa aplicada e auditoria espacial](docs/pesquisa_aplicada.md) e
[requisitos e pendências](docs/requisitos_e_pendencias.md). O controle conjunto
e a referência da planilha exigem validação dos IDs, movimentos, pedestres e
planos; a demonstração executável usa um sinal nominal.

Este pipeline executa o SUMO por TraCI, gera demanda de teste e registra os resultados de cada execução. O piloto PPO ajusta apenas a duração dos verdes selecionados; amarelo e vermelho de limpeza permanecem fixos. A planilha está em `dados/planos/RondonNorte.xlsx`; a rede viária está em `dados/rede/`.

Os [quatro requisitos revisados e a lista do que falta](docs/requisitos_e_pendencias.md) definem quando o simulador de pesquisa poderá ser considerado completo para os nove cruzamentos.

O passo a passo dos comandos e a explicação do treinamento estão em [docs/treinamento.md](docs/treinamento.md).
O treino PPO e a interface estão documentados em [docs/ppo_interface.md](docs/ppo_interface.md).
O entendimento do sistema completo, a arquitetura PPO proposta e as etapas ainda pendentes estão em [docs/arquitetura_ppo.md](docs/arquitetura_ppo.md).
Para entender a configuração-base, comece por [docs/configuracoes_sumo.md](docs/configuracoes_sumo.md); a lista integral das 462 opções está no [anexo técnico](docs/catalogo_completo_sumo.md).
Para acompanhar os parâmetros usados em uma execução, leia [docs/parametros_simulacao.md](docs/parametros_simulacao.md); os argumentos e chamadas completos estão na [referência detalhada](docs/referencia_parametros.md).

## Organização

```text
SistemaDeSemaforos/
├── pipeline.py                 # inspeção, referência, busca antiga e PPO
├── interface.py                # interface Streamlit
├── config/cenario.json         # parâmetros editáveis do cenário
├── dados/
│   ├── planos/RondonNorte.xlsx # tempos recebidos
│   ├── rede/*.net.xml          # mapa SUMO
│   └── inventario.json         # resumo da planilha e da rede
├── semaforos/
│   ├── configuracao.py         # caminhos e validações gerais
│   ├── planos.py               # leitura da planilha
│   ├── rede.py                 # semáforos e fases da rede
│   ├── demanda.py              # geração de veículos
│   ├── simulacao.py            # execução TraCI e métricas
│   ├── treinamento.py          # busca anterior por modelo substituto
│   ├── ambiente_ppo.py         # Gymnasium com SUMO/TraCI
│   └── ppo.py                  # treino e avaliação PPO
├── docs/                       # catálogo completo de opções SUMO
└── resultados/                 # saídas locais, fora do Git
```

## Preparação

Instale o SUMO e coloque `sumo` no `PATH` ou defina `SUMO_HOME`. Instale as dependências com `python -m pip install -r requirements.txt`. O ambiente Anaconda desta máquina já tem `openpyxl`, `sumolib`, `traci` e `torch` e foi usado nas verificações.

Na pasta `SistemaDeSemaforos`, execute:

```powershell
python pipeline.py inspect > dados/inventario.json
python pipeline.py run
python pipeline.py train
python pipeline.py ppo-train
python -m streamlit run interface.py
```

`inspect` lista os nove cruzamentos e os 36 planos da planilha, além dos IDs, coordenadas, links controlados, fases dos 28 semáforos e contagens de rotas, veículos e fluxos da rede. `run` executa o plano base do **arquivo de rede** para os IDs em `targets`. `train` é um piloto com modelo substituto, **não PPO**; executa várias tentativas e grava `dataset.jsonl`, `best_candidate.json` e `surrogate_model.pt`. Para reaplicar a melhor configuração:

```powershell
python pipeline.py run --candidate resultados/PASTA_DO_TREINO/best_candidate.json
```

`ppo-train` usa Gymnasium, Stable-Baselines3 e TraCI para ajustar dinamicamente o verde durante a simulação. O modelo fica em `ppo_model.zip`. Para comparar PPO e programa original da rede com as mesmas sementes:

```powershell
python pipeline.py ppo-eval --model resultados/PASTA_PPO/ppo_model.zip
```

A interface ainda apresenta **um cruzamento nominal**. Não interprete essa execução como controle validado dos nove cruzamentos.

Cada execução usa uma pasta própria em `resultados/`. Os arquivos incluem `inputs.json`, rotas geradas, `tripinfo.xml`, `summary.xml`, `statistics.xml` e `metrics.json`. O diretório é ignorado pelo Git.

## Configuração da simulação

Edite `config/cenario.json`. As opções utilizadas pelo pipeline são:

| Campo | Significado |
| --- | --- |
| `network`, `plans`, `plan_id` | Rede SUMO, planilha de referência e plano da planilha a consultar. O plano da planilha ainda não é aplicado à rede. |
| `duration_seconds`, `step_seconds`, `seeds` | Duração, passo da simulação e sementes reproduzíveis. |
| `demand.mode: random` | Viagens sintéticas geradas por `randomTrips.py`; `vehicles_per_hour` define a taxa total aproximada. |
| `demand.mode: flows` | Fluxos por par de vias com `from_edge`, `to_edge` e `vehicles_per_hour`. Cada entrada pode ter taxa própria. |
| `demand.mode: edge_volumes` | Volume por via de entrada (`from_edge`, `vehicles_per_hour`); `to_edge` é opcional. Sem destino, o gerador sorteia uma saída alcançável e a identifica como sintética. |
| `targets` | Semáforos e índices dos verdes cujas durações o piloto poderá alterar. Amarelo e limpeza permanecem fixos. |
| `training` | Número de tentativas, início aleatório, candidatos, mínimos por tipo de fase e penalidade por veículo que não terminou. |

Exemplo de demanda por via, após identificar IDs válidos no inventário ou na rede:

```json
"demand": {
  "mode": "flows",
  "flows": [
    {"from_edge": "ID_DA_VIA_DE_ENTRADA", "to_edge": "ID_DA_VIA_DE_SAIDA", "vehicles_per_hour": 450}
  ]
}
```

As rotas de cada semente são iguais entre candidatos, para permitir comparação. Ao trocar as taxas, execute `train` novamente: o modelo salvo representa apenas as simulações com a demanda usada no treino anterior.

Na interface, escolha **Volume por via** para preencher a tabela de veículos/h. As quatro entradas do sinal nominal aparecem inicialmente com zero e outras vias da rede podem ser adicionadas. Os nomes de rua dessas entradas estão vazios no XML, por isso a tabela usa IDs SUMO. Para um horizonte de 600 s, por exemplo, 360 veículos/h em uma via geram aproximadamente 60 partidas dessa via, **não** 360 em cada rota. O total é arredondado ao inteiro mais próximo; congestionamento pode adiar a entrada efetiva. Destinos automáticos são saídas alcançáveis sorteadas uniformemente entre as opções, não conversões medidas. O arquivo `demand_manifest.json` registra os veículos planejados e a origem de cada destino.

O mesmo modo pode ser salvo em um JSON de cenário para uso pela linha de comando:

```json
"demand": {
  "mode": "edge_volumes",
  "edge_volumes": [
    {"from_edge": "1156272393#6", "vehicles_per_hour": 360},
    {"from_edge": "1156717168", "vehicles_per_hour": 180, "to_edge": "ID_DA_SAIDA"}
  ]
}
```

Retire `to_edge` para usar uma saída sintética alcançável. Os IDs são da rede SUMO fornecida; associe-os às contagens reais antes de calibrar o cenário.

## O que a rede e a planilha representam

A planilha traz nove cruzamentos, com planos 2, 4, 16 e 24. Cada plano informa defasagem, duração de verde, amarelo, limpeza e ciclo por estágio. A rede atual tem 28 semáforos. Ela não traz nomes de ruas para a maioria dos IDs, então a associação dos outros oito cruzamentos precisa de conferência geográfica.

O único ID nominal claramente associado é `FAM_RONDON_PARANA`, incluído em `targets` como demonstração funcional. **A modelagem não coincide com a planilha:** no plano 4, a planilha registra quatro estágios e ciclo de 110 s; o programa SUMO desse ID tem duas fases verdes, duas amarelas, duas fases totalmente vermelhas e ciclo de 90 s. O piloto só varia os verdes 0 e 3; os estados, a ordem, amarelos e limpezas ficam fixos. O vermelho observado em uma via também depende do tempo verde dado à via conflitante. É preciso reconciliar a diferença entre planilha e rede antes de interpretar o resultado como otimização dos sinais reais da Rondon Norte.

O treino usa primeiro busca aleatória e depois uma rede neural pequena como **modelo substituto**: ela estima a pontuação de novas combinações de tempos, que são então avaliadas pelo SUMO. Isso é uma base experimental, não prova de ótimo global. A pontuação é a soma de veículos parados, em veículo-segundos nas vias controladas, mais uma penalidade por veículo que entrou e não concluiu a rota no tempo simulado. Os arquivos XML permitem outras métricas. Com demanda aleatória, as pontuações servem para testar o pipeline, não para recomendar tempos à cidade.

## Todas as opções do SUMO instalado

`docs/opcoes_sumo_1.27.1.txt` contém a saída integral de `sumo --help` desta instalação. `docs/modelo_todas_opcoes.sumocfg` é o template comentado de configuração gerado pelo próprio SUMO 1.27.1. Para atualizar após trocar de versão:

```powershell
python pipeline.py options > docs/opcoes_sumo_atual.txt
sumo --save-template docs/modelo_todas_opcoes_atual.sumocfg --save-commented
```

O template é um **catálogo**, não a configuração usada em cada execução. As entradas efetivamente usadas estão em `config/cenario.json` e nos `inputs.json` de cada simulação. As categorias do catálogo incluem arquivos de entrada, saídas, tempo, roteamento, comportamento de veículos, semáforos, pedestres, emissões, dispositivos, aleatoriedade e relatórios.
