# Pipeline SUMO: Rondon Norte

Este pipeline executa o SUMO sem interface, gera demanda de teste, registra os resultados de cada execução e testa durações de verde, amarelo e vermelho de limpeza dos semáforos selecionados. A planilha está em `dados/planos/RondonNorte.xlsx`; a rede viária está em `dados/rede/`.

O passo a passo dos comandos e a explicação do treinamento estão em [docs/treinamento.md](docs/treinamento.md).
Para entender a configuração-base, comece por [docs/configuracoes_sumo.md](docs/configuracoes_sumo.md); a lista integral das 462 opções está no [anexo técnico](docs/catalogo_completo_sumo.md).
Para acompanhar os parâmetros usados em uma execução, leia [docs/parametros_simulacao.md](docs/parametros_simulacao.md); os argumentos e chamadas completos estão na [referência detalhada](docs/referencia_parametros.md).

## Organização

```text
SistemaDeSemaforos/
├── pipeline.py                 # comandos inspect, options, run e train
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
│   └── treinamento.py          # seleção de durações pela rede neural
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
```

`inspect` lista os nove cruzamentos e os 36 planos da planilha, além dos IDs, coordenadas, vias de entrada e fases dos 28 semáforos da rede. `run` executa o plano base do **arquivo de rede** para os IDs em `targets`. `train` executa várias tentativas e grava `dataset.jsonl`, `best_candidate.json` e o modelo substituto `surrogate_model.pt`. Para reaplicar a melhor configuração:

```powershell
python pipeline.py run --candidate resultados/PASTA_DO_TREINO/best_candidate.json
```

Cada execução usa uma pasta própria em `resultados/`. Os arquivos incluem `inputs.json`, rotas geradas, `tripinfo.xml`, `summary.xml`, `statistics.xml` e `metrics.json`. O diretório é ignorado pelo Git.

## Configuração da simulação

Edite `config/cenario.json`. As opções utilizadas pelo pipeline são:

| Campo | Significado |
| --- | --- |
| `network`, `plans`, `plan_id` | Rede SUMO, planilha de referência e plano da planilha a consultar. O plano da planilha ainda não é aplicado à rede. |
| `duration_seconds`, `step_seconds`, `seeds` | Duração, passo da simulação e sementes reproduzíveis. |
| `demand.mode: random` | Viagens sintéticas geradas por `randomTrips.py`; `vehicles_per_hour` define a taxa total aproximada. |
| `demand.mode: flows` | Fluxos por par de vias com `from_edge`, `to_edge` e `vehicles_per_hour`. Cada entrada pode ter taxa própria. |
| `targets` | Semáforos e índices das fases cujas durações o treino poderá alterar. |
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

## O que a rede e a planilha representam

A planilha traz nove cruzamentos, com planos 2, 4, 16 e 24. Cada plano informa defasagem, duração de verde, amarelo, limpeza e ciclo por estágio. A rede atual tem 28 semáforos. Ela não traz nomes de ruas para a maioria dos IDs, então a associação dos outros oito cruzamentos precisa de conferência geográfica.

O único ID nominal claramente associado é `FAM_RONDON_PARANA`, incluído em `targets` como demonstração funcional. **A modelagem não coincide com a planilha:** no plano 4, a planilha registra quatro estágios e ciclo de 110 s; o programa SUMO desse ID tem duas fases verdes, duas amarelas, duas fases totalmente vermelhas e ciclo de 90 s. O código varia a duração das seis fases, mas não muda seus estados nem sua ordem. Os intervalos amarelos e totalmente vermelhos não podem ficar menores que os tempos atuais da rede. O vermelho observado em uma via também depende do tempo verde dado à via conflitante. É preciso reconciliar a diferença entre planilha e rede antes de interpretar o resultado como otimização dos sinais reais da Rondon Norte.

O treino usa primeiro busca aleatória e depois uma rede neural pequena como **modelo substituto**: ela estima a pontuação de novas combinações de tempos, que são então avaliadas pelo SUMO. Isso é uma base experimental, não prova de ótimo global. A pontuação é a soma de veículos parados, em veículo-segundos nas vias controladas, mais uma penalidade por veículo que entrou e não concluiu a rota no tempo simulado. Os arquivos XML permitem outras métricas. Com demanda aleatória, as pontuações servem para testar o pipeline, não para recomendar tempos à cidade.

## Todas as opções do SUMO instalado

`docs/opcoes_sumo_1.27.1.txt` contém a saída integral de `sumo --help` desta instalação. `docs/modelo_todas_opcoes.sumocfg` é o template comentado de configuração gerado pelo próprio SUMO 1.27.1. Para atualizar após trocar de versão:

```powershell
python pipeline.py options > docs/opcoes_sumo_atual.txt
sumo --save-template docs/modelo_todas_opcoes_atual.sumocfg --save-commented
```

O template é um **catálogo**, não a configuração usada em cada execução. As entradas efetivamente usadas estão em `config/cenario.json` e nos `inputs.json` de cada simulação. As categorias do catálogo incluem arquivos de entrada, saídas, tempo, roteamento, comportamento de veículos, semáforos, pedestres, emissões, dispositivos, aleatoriedade e relatórios.
