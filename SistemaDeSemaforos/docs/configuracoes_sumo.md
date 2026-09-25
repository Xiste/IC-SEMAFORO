# 2. Configurações-base do SUMO

## O que o projeto carrega hoje?

Uma execução começa com três fontes diferentes:

| Fonte | O que fornece | Onde está |
| --- | --- | --- |
| **Cenário do projeto** | Duração, veículos de teste, sementes e semáforos a treinar. | [`config/cenario.json`](../config/cenario.json) |
| **Rede SUMO** | Ruas, conexões e programa original dos semáforos. | [`dados/rede/`](../dados/rede/uberlandia.vehicular.families.16_2_4.net.xml) |
| **Padrões do SUMO** | Opções que o pipeline não definiu, como partes do comportamento dos veículos. | Instalação do `sumo` 1.27.1 |

A [planilha RondonNorte](../dados/planos/RondonNorte.xlsx) também é lida, mas seus tempos são guardados **como referência**. O programa da rede ainda não corresponde aos quatro estágios da planilha; escolher `plan_id: 4` não aplica automaticamente esse plano ao SUMO.

## Valores-base da simulação

| Configuração | Valor atual | Para mudar |
| --- | --- | --- |
| Tempo de simulação | **600 s**, com passos de **1 s** | `duration_seconds` e `step_seconds` no cenário |
| Veículos de teste | **360 veículos/h** distribuídos pelo gerador de viagens | `demand` no cenário |
| Semente | **11**, para repetir o mesmo experimento | `seeds` no cenário |
| Semáforo treinado | `FAM_RONDON_PARANA` | `targets` no cenário |
| Fases treinadas | **0 a 5**: dois verdes, dois amarelos, dois intervalos totalmente vermelhos | `targets.phase_indices` no cenário |
| Tempos originais | **41 + 3 + 1 + 41 + 3 + 1 = 90 s** por ciclo | Programa do semáforo na rede SUMO |

O código muda **a duração** das fases selecionadas. Ele mantém a ordem e o estado de cada fase. O amarelo e o intervalo totalmente vermelho podem ser prolongados, mas não ficam abaixo do tempo original da rede. O vermelho visto por uma via também depende de quanto verde é dado à via conflitante.
## Que outras configurações existem?

As opções se dividem em três níveis:

1. **Cenário do projeto:** você pode trocar rede, planilha de referência, duração, sementes, quantidade de veículos, fluxos por via, semáforos selecionados, limites de duração e parâmetros do treino. Todos os campos usados estão explicados no [item 3](parametros_simulacao.md).
2. **Opções do executável `sumo`:** há **462 opções principais em 27 categorias** nesta instalação, incluindo entradas, saídas, roteamento, comportamento da simulação, emissões, dispositivos e comunicação. O pipeline define dez delas diretamente; TraCI, a interface usada pelo Python para controlar o SUMO, acrescenta uma porta de comunicação. Veja a [lista completa com tipo, valor no template e aliases](catalogo_completo_sumo.md).
3. **Dados internos dos arquivos SUMO:** características de vias, veículos, rotas e programas semafóricos ficam nos arquivos XML. Elas não são campos do `config/cenario.json` nem parte da lista de opções do executável.

As demais opções do executável seguem o comportamento padrão da instalação. Nem todas fazem sentido para o cenário atual; algumas exigem arquivos adicionais ou a interface gráfica. A [ajuda integral do SUMO](opcoes_sumo_1.27.1.txt) também está salva em texto.

## Como conferir antes de rodar

Abra um PowerShell na pasta `SistemaDeSemaforos`:

```powershell
python pipeline.py inspect
python pipeline.py options
python pipeline.py run --config config/cenario.json
```

`inspect` mostra o que veio da planilha e quais fases existem na rede. `options` imprime a lista de opções do executável instalado. `run` executa a configuração-base sem abrir a interface. O [item 3](parametros_simulacao.md) mostra exatamente quais parâmetros são enviados nessa execução.
