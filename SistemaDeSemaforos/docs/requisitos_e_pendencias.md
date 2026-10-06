# Requisitos do pipeline e critérios de conclusão

Escopo: simulador **de pesquisa** para os nove cruzamentos de Rondon Norte.
"Pronto" significa produzir experimentos reproduzíveis e comparações
confiáveis no SUMO. Implantação em semáforos reais exigiria homologação
operacional adicional. Nenhuma política tem garantia de ótimo global.

## R1 — Carregar e validar o cenário

O pipeline deve carregar a rede SUMO, a planilha de planos, a versão das
ferramentas, os nove cruzamentos e a demanda. Deve conferir, para cada
cruzamento, nome, ID SUMO, faixas, links, movimentos, estágios, pedestres,
tempos de segurança e divergências planilha–rede. Rotas devem ser alcançáveis.
Os outros semáforos da rede devem continuar em seus programas originais.

**Aceite:** relatório de validação dos nove cruzamentos sem associação
presumida; cada cenário deve registrar rede, plano, demanda, semente e
arquivos gerados. Uma divergência não resolvida deve impedir o uso daquele
plano como referência validada.

**Estado: parcial.** A leitura encontra nove cruzamentos, 28 `tlLogic` e
nenhuma demanda no XML. A interface aceita taxa global sintética, volumes por
via e pares origem–destino; valida a conectividade de rotas. Só
`FAM_RONDON_PARANA` tem associação nominal. Seu programa SUMO tem dois verdes
e ciclo de 90 s; o plano 4 da planilha tem quatro estágios e 110 s.

## R2 — Catalogar configurações e registrar as usadas

O catálogo deve declarar versão e cobertura. Separar **todas as opções de
linha de comando do executável `sumo` instalado** dos atributos da rede,
definições de demanda, chamadas TraCI, parâmetros PPO e escolhas do
experimento. Para cada parâmetro usado numa execução, registrar valor,
origem, tipo, unidade, limites e se pode mudar durante a simulação.

**Aceite:** catálogo regenerável para a versão instalada e manifesto da
execução que permita reconstruir comandos, configuração efetiva, alterações
TraCI e hiperparâmetros. "Todas" só pode ser afirmado dentro da cobertura
declarada; uma lista de opções do executável não é um catálogo de todas as
APIs e formatos SUMO.

**Estado: parcial.** O [catálogo existente](catalogo_completo_sumo.md)
lista 462 opções principais do `sumo` 1.27.1, geradas do template local.
O `manifest.json` do PPO registra parte do cenário e hiperparâmetros. A
[referência de parâmetros](referencia_parametros.md) descreve principalmente
o pipeline anterior e está desatualizada para PPO e volume por via. Faltam
inventário TraCI/rede/demanda completo e registro automático de todos os
valores efetivos e versões por experimento.

## R3 — Executar, avaliar e medir custo do PPO

O pipeline deve iniciar SUMO/TraCI sem intervenção manual, treinar PPO,
permitir cancelamento e executar referência e avaliação com demanda
equivalente. Configurar separadamente `n_epochs=10`, `n_steps`, tamanho do
minibatch, `total_timesteps`, intervalo de decisão, duração do episódio e
sementes. Usar cenários e sementes de avaliação separados dos usados na seleção
da política e testar repetibilidade. Medir tempo simulado, tempo real e
recursos usados em pilotos e na execução completa.

**Aceite:** os nove cruzamentos validados são controlados; treino e avaliação
terminam e produzem modelo, logs e comparação em várias sementes/cenários.
Existe medição de custo no hardware usado. Dez épocas significam dez passadas
de atualização por lote, não dez episódios.

**Estado: parcial.** PPO, ambiente Gymnasium, interface e comparação com o
programa da rede funcionam para **um** sinal nominal. Um piloto local com
`n_epochs=10`, `n_steps=16`, `batch_size=8`, `total_timesteps=16` e episódios
de 60 s concluiu um episódio e levou 8,95 s dentro de `train_ppo` (cerca de
19 s para o comando completo, incluindo importação/inicialização). Isso
mostra que 10 épocas executam neste piloto; não estima de modo confiável o
custo de 2048 passos nem de nove sinais. Não houve teste de convergência,
avaliação independente com várias sementes ou medição sistemática de CPU/RAM.

## R4 — Relatar métricas e comparar controladores

Registrar métricas essenciais e opcionais com origem, unidade, frequência,
cálculo, agregação e limitações. Distinguir valores TraCI/SUMO de derivados.
Incluir veículos planejados, carregados, inseridos, concluídos, ativos e
aguardando inserção, sem somar repetidamente contadores acumulados. Comparar
referência validada e PPO nas mesmas condições, com resultados por execução,
cruzamento e conjunto, médias, dispersão, gráficos, falhas e viagens
incompletas. Coleta opcional mais cara deve ser selecionável.

**Aceite:** CSV/JSON e relatório legível permitem reproduzir e auditar cada
comparação; viagens pendentes aparecem junto com as concluídas; nenhuma
conclusão de superioridade se baseia em uma única execução.

**Estado: parcial.** O PPO salva recompensa, partidas, chegadas, espera
incremental, fila aproximada, veículo-segundos ativos e veículos pendentes;
`tripinfo.xml` registra viagens incompletas. A avaliação gera `runs.csv` e
JSON para PPO e programa da rede. Esses arquivos ainda não fornecem um
relatório completo: faltam métricas por cruzamento, tempos de viagem
extraídos, atraso, velocidade, ocupação, vazão, paradas, emissões, consumo,
eventos, tempos semafóricos, CPU/RAM, média/dispersão entre repetições,
gráficos e limites de qualidade dos dados. A referência da planilha ainda
não pode ser aplicada como plano validado.

## Pendências para considerar o simulador completo

1. **Dados e validação operacional:** mapear os oito sinais restantes;
   reconciliar estágios e tempos da planilha com a rede; validar pedestres,
   conflitos, amarelo, limpeza, verde máximo e tempo máximo sem atendimento.
2. **Demanda representativa:** associar cada contagem futura de rua ao ID de
   via; definir perfil horário, tipos de veículo e destinos/conversões medidos
   ou marcar claramente as hipóteses sintéticas; conferir entrada real versus
   planejada e guardar cenários de treino e avaliação distintos.
3. **Experimento completo:** ampliar o controlador para os nove sinais após
   R1, calibrar escalas da recompensa com a referência, executar piloto de
   custo com 10 épocas e depois treino suficiente, avaliar várias sementes e
   comparar com referência da planilha validada e controlador simples.
4. **Observabilidade e relatório:** versionar todos os parâmetros efetivos,
   expandir as métricas e a exportação, gerar gráficos e estatísticas de
   dispersão, registrar erros e recursos e verificar a interface ponta a
   ponta em treinamento longo e cancelamento.

O código atual é um **piloto executável**, não um sistema validado para os
nove cruzamentos. As pendências 1 e 2 dependem de informações de campo ou
de validação do responsável pela rede; as demais são trabalho de software e
experimentos reproduzíveis.

## Estado após a implementação de outubro de 2026

R1 continua parcial: `pipeline.py mapping` audita os nove nomes, links, fases, ciclos e declarações de segurança. O arquivo `config/mapeamento.json` é uma lista de conferência; os oito IDs restantes e a reconciliação do plano da planilha não foram fornecidos. O PPO conjunto exige validação antes de iniciar.

R2 avançou: `manifest.json` guarda configuração de treino, versões, hashes e hiperparâmetros efetivos; cada episódio guarda comando SUMO, configuração efetiva, demanda gerada e ações TraCI quando habilitadas. O catálogo integral de opções do SUMO instalado continua separado do inventário dos valores usados.

R3 avançou: a avaliação usa sementes de treino e avaliação distintas e compara os controladores na mesma demanda planejada em cada semente. A arquitetura aceita múltiplos alvos, mas o treino com nove sinais aguarda R1. Uma avaliação de três sementes curtas verificou os arquivos e não produziu chegadas; falta estudo de desempenho com horizontes e demanda representativos.

R4 avançou: existem métricas por sinal, viagem concluída, filas, velocidades, ocupação, fases, eventos, CPU/RAM e emissões opcionais; média, desvio padrão, gráfico e relatório. Veja [catálogo de métricas](catalogo_metricas.md). A referência ainda é o programa da rede, pois o plano da planilha não pode ser aplicado fielmente antes da reconciliação. Dados reais de volume e proporções de conversão continuam pendentes.
