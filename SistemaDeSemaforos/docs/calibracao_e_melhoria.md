# Calibrar demanda e medir melhoria na interface

O fluxo confere separadamente o ajuste das rotas e os fluxos realizados no SUMO. Uma comparação informa ganhos e perdas medidos; o software não força um resultado positivo.

## Preparar a demanda

1. Selecione o piloto ou prepare/carregue um cenário novo dos nove cruzamentos.
2. Em **Modelo**, escolha **Volume por via** e **Contagens observadas: calibrar entradas da rede**.
3. Abra **Importar contagens medidas** e envie o CSV/XLSX. O arquivo local `dados/medicoes/Medicoes_5_6.csv` é aceito.
4. Para arquivos com `hora_inicio` e `hora_fim`, marque **Selecionar período das contagens** e informe início/fim no horário registrado no arquivo. Apenas janelas inteiras dentro do intervalo entram no cálculo; não há divisão artificial de contagens nas bordas. Sem filtro, a taxa é a média das janelas do arquivo, podendo misturar horários/dias.
5. Associe cada sensor à via e sentido corretos e clique **Aplicar contagens associadas**. O sistema não infere essas associações pelos nomes. A origem do arquivo, hash, período e associação ficam registrados na configuração da execução. A taxa usa o tempo efetivamente coberto pelas janelas, não preenche lacunas sem observação.
6. Ajuste a duração, sementes de avaliação e tolerância. Clique **Calibrar demanda e conferir contagens**. O painel conserva o ajuste enquanto a rede e a demanda não forem modificadas.

O ajuste NNLS escolhe volumes não negativos para rotas que entram e saem nas bordas da rede e passam pelos trechos medidos. O mesmo veículo pode explicar contagens em ruas consecutivas; não é gerado novamente em cada sensor. Destinos continuam sintéticos, pois contagens isoladas não determinam uma matriz origem/destino única.

## Conferir no SUMO

Clique **Validar demanda calibrada no SUMO**. O programa de referência roda em todas as sementes de avaliação. Na seção **Calibração e evidência de melhoria**, examine:

- Volume medido, volume ajustado nas rotas e fluxo realizado pelos detectores virtuais.
- Maior erro por trecho entre sementes e aprovação na tolerância escolhida.
- Janelas/arquivo de origem quando disponíveis.

A validação requer cobertura de todos os trechos e sementes previstos, episódios completos e ausência de cancelamento. A aprovação refere-se aos fluxos cadastrados; não certifica geometria, destinos, planos reais ou cobertura de toda a cidade. Os detectores são posicionados no meio dos trechos, portanto a posição de um detector físico ainda deve ser considerada na interpretação.

Se as rotas ajustarem as contagens mas o fluxo realizado ficar abaixo do esperado, confira viagens que aguardam partida, congestionamento, rotas e o tempo de percurso até os sensores. Iniciar a simulação vazia e terminar com veículos em viagem pode reduzir o fluxo medido no horizonte. Não aumente simplesmente a tolerância para ocultar diferenças. Não há ajuste automático iterativo de parâmetros de comportamento ou otimização da geometria nesta implementação.

## Comparar controles

Use **Comparar referência e controle por filas sem treinamento** para executar uma comparação sem modelo. Para incluir PPO, treine um modelo compatível e use **Avaliar PPO e referência**. A avaliação compara referência, controle por filas e modelo com as mesmas sementes.

O painel mostra valores médios antes/depois, benefício absoluto, percentual, quantidade de sementes com melhora/piora, intervalo de confiança exploratório e diferenças por cruzamento. Percentual positivo significa melhora; se a referência vale zero, o percentual fica vazio e os valores absolutos permanecem disponíveis. Tempo médio de viagem só considera viagens concluídas.

Para a conclusão **Melhoria consistente nas sementes simuladas**, exige-se:

- Pelo menos três sementes pareadas, com demanda canônica idêntica (viagens, horários, tipos e pedestres) e horizonte igual entre controles.
- Comparação completa, incluindo todas as sementes previstas, sem cancelamento.
- Redução de fila acumulada global e espera, ambas com limite inferior positivo do IC t pareado de 95%.
- Nenhuma perda de chegadas nem aumento de viagens incompletas/partidas pendentes em qualquer semente, sem colisões ou teletransportes nos dois controles.
- Quando houver pedestres, nenhuma redução de chegadas nem aumento de espera agregada.
- Em demanda por contagens, fluxos realizados da referência dentro da tolerância cadastrada em todos os trechos e sementes.

Outros resultados recebem mensagens específicas de evidência limitada, falta de melhoria simultânea, perda de atendimento, comparação incompleta ou calibração inadequada. As tabelas mantêm ganhos e perdas mesmo quando os critérios para uma conclusão favorável não são cumpridos.

Os intervalos são exploratórios, por métrica, sem ajuste para múltiplas comparações, e pressupõem diferenças aproximadamente normais. Sementes de avaliação medem a variabilidade da simulação; elas não substituem treinos independentes ou validação em campo. A comparação pode mostrar melhora global com perdas locais, que devem ser revisadas na tabela por cruzamento. A conclusão não certifica implantação semafórica real.

## Arquivos e comandos

Resultados atuais e anteriores exibem o mesmo painel quando contêm `diagnostico.json`. São exportados também `melhorias.csv`, `melhorias_cruzamentos.csv` e `validacao_demanda.csv` quando houver dados correspondentes. `summary.json` e `report.md` incluem as conclusões. Resultados antigos sem diagnóstico permanecem acessíveis pelos relatórios anteriores.

```powershell
.\.venv-verificacao\Scripts\python.exe pipeline.py validate-demand --config CAMINHO_DO_CENARIO.json
.\.venv-verificacao\Scripts\python.exe pipeline.py compare-baselines --config CAMINHO_DO_CENARIO.json
.\.venv-verificacao\Scripts\python.exe pipeline.py rl-eval --config CAMINHO_DO_CENARIO.json --model CAMINHO_DO_MODELO.zip
```

Os comandos criam novas saídas. `validate-demand` exige `demand.mode=observed_counts`; `compare-baselines` funciona também com demanda aleatória ou OD, mas nesse caso não há validação por contagens observadas.

## Demonstrações executadas em 07/10/2026

Foram executadas duas comparações dos nove cruzamentos/17 controladores, com sementes 101, 102 e 103, referência e controle por filas. As contagens dos dois trechos usados nestes testes são **sintéticas**, não são os valores dos sensores físicos 5/6. Não foi fornecida sua associação nem o período real de interesse.

| Caso | Contagem sintética por trecho | Horizonte | Resultado |
|---|---:|---:|---|
| Carga baixa | 120 veículos/h | 1.800 s | Calibração aprovada na tolerância de 20%; maior erro realizado da referência 6,67%. Fila e espera médias reduziram 10,94%, sem perda de chegadas. |
| Carga alta | 1.200 veículos/h | 900 s | Ajuste matemático exato, mas fluxos da referência com erro de até 74,67%. Fila e espera médias reduziram cerca de 13,51%, sem certificar a demanda na tolerância. |

No caso de carga baixa, a fila acumulada média passou de 2.926,33 para 2.606,33 veículo·s, e as chegadas permaneceram em 51 veículos por episódio. A redução ocorreu nas três sementes, mas o IC t de 95% do benefício foi de −259,38 a 899,38 veículo·s. Portanto, a conclusão publicada é **Melhoria média observada; evidência ainda limitada**, sem afirmar consistência estatística ou melhoria no trânsito real. Ambas as comparações preservaram viagens/horizontes entre controles e não registraram colisões ou teletransportes.

Abra **Abrir relatórios de execuções anteriores** e selecione:

- `demonstracao_calibracao_20261007_baixa_carga/comparacao`: ajuste aprovado e melhoria média observada.
- `demonstracao_calibracao_20261007/comparacao_v2`: exemplo de ajuste matemático que não reproduz o fluxo realizado.

Os cenários e resultados foram preservados em `resultados/`. Houve também execução real de `validate-demand` com duas sementes e horizonte de 20 s para conferir o comando; esse teste curto não valida trânsito ou desempenho. Testes de integração de PPO continuam verificando treino/salvamento/carregamento/avaliação, mas não foi feito novo treino longo nesta implementação.
