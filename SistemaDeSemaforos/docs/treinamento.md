# Treinamento dos semáforos com SUMO

Este guia descreve o treinamento implementado em `semaforos/treinamento.py` e os comandos para executá-lo. O SUMO roda sem abrir a interface gráfica. O cenário editável fica em `config/cenario.json`.

## 1. Preparar o ambiente

Abra o PowerShell na pasta do projeto:

```powershell
cd C:\Projetos\IC-SEMAFORO\SistemaDeSemaforos
```

É necessário ter o executável `sumo` no `PATH` ou definir `SUMO_HOME`. Nesta máquina, a instalação pode ser indicada assim:

```powershell
$env:SUMO_HOME = 'C:\Program Files (x86)\Eclipse\Sumo'
& "$env:SUMO_HOME\bin\sumo.exe" --version
```

Instale as dependências no Python que será usado para rodar o pipeline:

```powershell
python -m pip install -r requirements.txt
python -c "import openpyxl, sumolib, traci, torch; print('Dependências disponíveis')"
```

Se `python` apontar para outro ambiente, use o caminho do Python desejado nos comandos. Por exemplo, nesta máquina o Python do Anaconda também tem as dependências:

```powershell
& 'C:\Users\cauan\anaconda3\python.exe' pipeline.py inspect
```

## 2. Conferir o cenário

Leia `config/cenario.json` antes do treino. Os campos principais são:

| Campo | Uso no treinamento |
| --- | --- |
| `network` e `plans` | Caminhos da rede SUMO e da planilha. São relativos à pasta `config/`. |
| `plan_id` | Seleciona o plano da planilha guardado como referência em cada execução; não altera automaticamente o programa SUMO. |
| `duration_seconds` e `step_seconds` | Tempo total e passo da simulação, em segundos. |
| `seeds` | Sementes usadas em todas as configurações candidatas. Use mais de uma para reduzir a dependência de uma única realização do tráfego. |
| `demand` | Tráfego sintético total (`random`) ou taxas por par de vias (`flows`). |
| `targets` | IDs SUMO dos semáforos e índices das fases cujas durações podem variar. |
| `training` | Quantidade de tentativas, início aleatório, candidatos avaliados pela rede neural, tempos mínimos por tipo de fase e penalidade por viagem não concluída. |

Para consultar os planos da planilha e as fases disponíveis na rede:

```powershell
python pipeline.py inspect > dados/inventario.json
```

O `inventario.json` contém IDs, vias de entrada e fases dos semáforos. Confira a associação geográfica antes de adicionar IDs a `targets`. A configuração entregue seleciona apenas `FAM_RONDON_PARANA`, com as fases 0 a 5: dois verdes, dois amarelos e dois intervalos totalmente vermelhos.

### Alterar a quantidade de veículos

O cenário inicial usa `demand.mode: "random"` e `vehicles_per_hour: 360`. Essa taxa é aproximada e distribuída pela rede pelo gerador do SUMO. Para definir uma taxa por via, troque a seção `demand` em `config/cenario.json` por, por exemplo:

```json
"demand": {
  "mode": "flows",
  "flows": [
    {
      "from_edge": "ID_DA_VIA_DE_ENTRADA",
      "to_edge": "ID_DA_VIA_DE_SAIDA",
      "vehicles_per_hour": 450
    }
  ]
}
```

Substitua os IDs pelos IDs reais de vias da rede e indique uma rota alcançável. Cada entrada de `flows` tem sua própria taxa. Depois de mudar a demanda, execute o treino novamente; o modelo salvo anteriormente foi ajustado ao cenário antigo.

## 3. Rodar a referência e o treinamento

Rode primeiro a configuração base da rede:

```powershell
python pipeline.py run
```

O programa imprime `mean_score` e cria uma pasta com data e hora em `resultados/`. Para dar um nome fixo à execução, indique uma pasta **que ainda não exista**:

```powershell
python pipeline.py run --output resultados/base_exemplo
```

Inicie o treinamento:

```powershell
python pipeline.py train
```

Ou indique a pasta de saída:

```powershell
python pipeline.py train --output resultados/treino_exemplo
```

Os comandos aceitam outro arquivo de cenário com `--config caminho/para/cenario.json`. Todos os caminhos `network` e `plans` dentro desse arquivo são resolvidos em relação à **pasta do próprio arquivo de cenário**.

## 4. Como o treinamento funciona

Cada tentativa escolhe uma duração, em segundos, para cada fase indicada em `targets`. O programa mantém os estados e a sequência de fases da rede, aplica as novas durações via TraCI, avança a simulação passo a passo e mede o resultado.

1. A tentativa `0` usa as durações originais de todas as fases selecionadas na rede SUMO.
2. As tentativas seguintes até `warmup_random - 1` escolhem durações aleatórias dentro dos limites. Para verde, o limite inferior é o maior entre `minimum_green_seconds` e 60% do tempo original; o superior é 140% do original. Para amarelo e totalmente vermelho, o limite inferior é pelo menos a duração atual da rede e os mínimos `minimum_yellow_seconds` e `minimum_all_red_seconds`. Esses dois tipos podem ser prolongados, mas não encurtados.
3. A partir da tentativa `warmup_random`, uma rede neural pequena aprende a relação entre os tempos testados e as pontuações obtidas. Ela estima a pontuação de `candidate_pool` novas combinações; a mais promissora é executada no SUMO e acrescentada aos dados de treino.
4. Após `iterations` tentativas, o pipeline grava a combinação com a menor pontuação medida. A rede neural ajuda a escolher o que testar; **a pontuação final sempre vem da simulação**.

Com os valores atuais, são 20 tentativas: a primeira é a referência, as tentativas 1 a 9 são aleatórias e as tentativas 10 a 19 usam a rede neural para escolher o candidato. A rede recebe as durações normalizadas de verde, amarelo e totalmente vermelho e aprende a prever a pontuação do cenário atual. Ela não controla os semáforos a cada segundo durante a simulação.

Na rede SUMO, um sinal pode permanecer vermelho enquanto outro movimento recebe verde ou amarelo. A duração total desse vermelho muda indiretamente quando as outras fases mudam. Os índices 2 e 5 de `FAM_RONDON_PARANA` são fases **totalmente vermelhas** de limpeza, que podem ter sua própria duração ajustada. Isso não equivale a configurar um tempo vermelho independente para cada via.

### Pontuação

Quando há semáforos em `targets`, a pontuação de cada execução é:

```text
veículo-segundos parados nas faixas controladas
+ veículos que entraram e não chegaram × unfinished_penalty_seconds
```

O pipeline calcula a média das pontuações das sementes em `seeds`. **Menor é melhor para essa função de avaliação.** `departed`, `arrived`, `unfinished` e os termos da pontuação aparecem em `metrics.json`. O tempo de viagem por veículo e outras medidas do SUMO ficam nos arquivos XML para análise posterior.

## 5. Ler e repetir o resultado

Dentro da pasta de treinamento:

| Arquivo | Conteúdo |
| --- | --- |
| `dataset.jsonl` | Uma linha por tentativa, com tempos testados, pontuação média e métricas por semente. |
| `best_candidate.json` | Durações de todas as fases selecionadas do melhor candidato **medido**. |
| `surrogate_model.pt` | Pesos da rede neural substituta ao fim do treino; não é um programa de semáforo pronto para uso. |
| `trial_000/seed_11/` etc. | Entradas, rotas, métricas e arquivos SUMO de cada tentativa e semente. |

Para repetir o melhor candidato em uma nova execução:

```powershell
python pipeline.py run --candidate resultados/treino_exemplo/best_candidate.json
```

Compare o `mean_score` impresso com o da execução base usando **o mesmo cenário e as mesmas sementes**. Para uma avaliação mais forte, inclua outras sementes em `config/cenario.json` e repita base e candidato. O comando `run` aceita `--candidate`; o comando `train` começa um treinamento novo e não retoma automaticamente um treino anterior.

## Limite do cenário atual

A planilha `RondonNorte.xlsx` registra quatro estágios e ciclo de 110 s para o plano 4 de Rondon Pacheco × Paraná. O programa `FAM_RONDON_PARANA` na rede SUMO tem dois verdes, dois amarelos, dois intervalos totalmente vermelhos e ciclo de 90 s. O treino altera as durações **da rede SUMO** e guarda o plano da planilha como referência; não reproduz automaticamente os tempos reais da planilha. Além disso, os veículos ainda são sintéticos. É preciso conferir os demais cruzamentos e reconciliar planilha e rede antes de usar os tempos encontrados como recomendação para o trânsito real.
