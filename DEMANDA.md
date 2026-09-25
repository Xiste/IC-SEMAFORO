# Demanda random

## O que é

A demanda random é um conjunto de viagens criado aleatoriamente para a rede
SUMO do projeto. Ela define quando cada veículo parte, sua origem, seu destino
e o caminho que poderá percorrer.

## Para que serve

Ela fornece uma entrada simples para testar a simulação enquanto ainda não
existem demandas baseadas em medições ou contexto real.

O comando de geração apenas prepara a demanda. Ele não inicia a simulação e
não executa treinamento ou controle de semáforos.

## Como gerar

Na raiz do repositório:

```bash
export SUMO_HOME=/usr/share/sumo
make demand-random
```

Os arquivos são gravados em `SistemaDeSemaforos/demandas/`.

## O que acontece quando o comando é executado

```text
make demand-random
        ↓
uma seed aleatória é escolhida
        ↓
randomTrips.py cria as viagens
        ↓
random.trips.xml
        ↓
duarouter calcula um caminho válido para cada viagem
        ↓
random.rou.xml
        ↓
arquivo pronto para ser carregado pelo SUMO
```

Esse fluxo corresponde à implementação atual: `randomTrips.py` grava o
arquivo de viagens e chama o `duarouter` para criar o arquivo de rotas.

## Por que existem dois arquivos

| Arquivo | Conteúdo | Quando é criado | Quem usa |
| --- | --- | --- | --- |
| `random.trips.xml` | Solicitações de viagem: origem, destino e horário de partida. | Na geração aleatória. | O `duarouter`, para calcular os caminhos. Também ajuda a inspecionar o que foi sorteado. |
| `random.rou.xml` | Veículos com as sequências de vias que formam suas rotas. | Depois do roteamento. | O SUMO, durante a simulação. |

O primeiro arquivo registra o problema de roteamento. O segundo registra o
resultado do roteamento e é a demanda final usada pela simulação. Manter os
dois deixa o processo verificável sem adicionar outra etapa ao código.

## De onde vêm as aproximadamente 4.800 viagens

Os valores padrão são:

- janela de partidas: `7200` segundos;
- intervalo entre partidas: `1.5` segundo;
- cálculo: `7200 / 1.5 = 4800` viagens solicitadas.

As partidas são regulares. A aleatoriedade está na escolha das origens e dos
destinos. O SUMO valida a conectividade da rede, portanto a quantidade de
veículos com rota pode ser menor que a quantidade solicitada.

## Por que os XMLs não entram no Git

O diretório `SistemaDeSemaforos/demandas/` está no `.gitignore` porque seus
arquivos são saídas automáticas e recriáveis. Eles mudam sempre que uma nova
seed é sorteada e não representam um cenário permanente do projeto.

A rede `.net.xml`, o código e a documentação continuam versionados. Se uma
demanda passar a ser um cenário fixo e permanente, ela deverá ser guardada em
outro local e versionada por uma decisão explícita.

## Parâmetros disponíveis

```bash
make demand-random DEMAND_ARGS='--duration 3600 --period 2 --output-dir /tmp/demanda-exemplo'
```

| Opção | Padrão | Função |
| --- | --- | --- |
| `--duration` | `7200` | Define a janela de partidas, em segundos. |
| `--period` | `1.5` | Define o intervalo entre partidas, em segundos. |
| `--net-file` | Rede do projeto | Escolhe a rede usada na geração e no roteamento. |
| `--output-dir` | `SistemaDeSemaforos/demandas` | Escolhe onde os dois XMLs serão gravados. |

Uma nova geração substitui os dois XMLs do diretório escolhido somente depois
de validar as novas saídas.

## Como o código está dividido

- `SistemaDeSemaforos/demand.py`: gera uma demanda random e devolve o caminho
  de `random.rou.xml`.
- `SistemaDeSemaforos/simulation.py`: recebe uma demanda pronta, executa o
  SUMO e coordena múltiplos episódios random quando solicitado.

Em uma execução com vários episódios random, `simulation.py` chama novamente
o gerador antes de cada episódio. Métodos futuros poderão gerar outros
arquivos e reutilizar a função `run_simulation` sem alterar o SUMO runner.

## Detalhes técnicos

- A seed é um inteiro sorteado a cada geração; não há seleção ou reprodução
  elaborada de seeds nesta etapa.
- A classe de veículo usada é `passenger`.
- As saídas são verificadas como XML antes de substituir uma demanda anterior.
- São necessários Python 3.10+, SUMO, `randomTrips.py`, `duarouter` e a variável
  `SUMO_HOME` configurada.

Os comandos de teste e de execução estão em
[COMANDOS_TESTE.md](COMANDOS_TESTE.md).
