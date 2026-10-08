# Análise funcional e capacidade de diagnóstico — 07/10/2026

O projeto executa simulações e produz métricas suficientes para investigar gargalos e comparar controles semafóricos no SUMO. Ainda não há evidência suficiente para afirmar que representa fielmente os nove cruzamentos reais ou que o PPO melhora o trânsito observado. Funcionamento do software e validade do experimento são conclusões distintas.

## Verificações desta análise

Executadas no ambiente `.venv`, sem alterar código, rede ou configurações originais:

- `pip check`: nenhuma incompatibilidade de dependências encontrada.
- `python -m unittest discover -s tests -v`: 34 testes aprovados em 284,057 s, incluindo integração SUMO, treino curto, salvamento/carregamento/avaliação do PPO conjunto, transições, importação, contagens, pedestres e episódios parciais.
- `scripts/verificar_interface_funcional.py`: aprovado; recuperação em duas sessões, gráficos, cancelamento e importações. Esse teste usa AppTest e dados/processos preparados pelo teste; não equivale a clicar manualmente em todas as telas.
- `pipeline.py measurements`: leitura das medições aprovada.
- Importação do CSV original por `parse_counts`: aprovada, com sensores 5 e 6 ainda sem aresta associada; taxas agregadas de aproximadamente 321,12 e 1.309,40 veículos/h. O arquivo inteiro mistura datas e horários entre junho e setembro; essas médias não representam automaticamente o horário de pico escolhido.
- Simulação de referência do piloto: horizonte de 600 s concluído, 60 veículos planejados e partidos, 48 chegados, 12 em viagem, zero partidas pendentes, colisões e teletransportes.
- Preparação nova dos nove cruzamentos e simulação de referência: 17 controladores, horizonte de 600 s concluído, 60 veículos planejados e partidos, 43 chegados, 17 em viagem, zero partidas pendentes, colisões e teletransportes.

Resultados preservados em `resultados/auditoria_20261007_referencia_piloto` e `resultados/auditoria_20261007_nove`. Cada execução usa uma semente, 11, e demanda aleatória de 360 veículos/h na rede. Não foi executado treinamento longo ou estudo comparativo novo de desempenho. O resultado de viagens incompletas aos 600 s não prova bloqueio: inclui veículos que partiram perto do fim. A média de viagem considera apenas chegadas.

## O que já permite fazer

Preparar o cenário conjunto, configurar/importar demanda e pedestres, simular sem treino, treinar/salvar/carregar PPO e comparar referência, controle reativo por filas e PPO em sementes de avaliação. Há métricas de espera, fila acumulada, pico de fila, chegadas, viagens incompletas, tempo de viagem, eventos e travessias. `intersections.csv` reúne faixas únicas por cruzamento; `signals.csv` detalha controladores e não deve ser somado indiscriminadamente quando houver faixas compartilhadas.

No teste conjunto desta análise, os maiores valores de fila acumulada foram:

| Cruzamento | Fila acumulada (veículo·s) | Pico de veículos parados |
|---|---:|---:|
| Rondon × Benjamim Magalhães | 320 | 2 |
| Rondon × Niterói | 242 | 2 |
| Cesário Alvim × Paraná | 172 | 1 |

Isso demonstra capacidade de localizar gargalos no cenário executado. Não estabelece prioridades de intervenção na cidade: o teste usa carga baixa, destinos sintéticos e uma semente. Os cenários piloto e conjunto usam redes/programas diferentes e seus números não constituem uma comparação isolada de qualidade do controle.

## Limites e prioridades

1. **Representatividade da demanda.** `config/cenario.json` usa demanda aleatória e apenas um alvo, Rondon × Paraná. O arquivo de medições contém dois sensores próximos de Niterói, não uma cobertura comprovada dos nove locais. Associar sensores a vias/sentidos, selecionar janelas comparáveis, revisar composição veicular e calibrar fluxos realizados em `flow_counts.csv`. Para horários distintos, criar cenários distintos; importar todo o arquivo atualmente gera uma taxa média por sensor.
2. **Referência operacional.** A comparação usa programas da rede, não aplica automaticamente o plano da planilha. O cenário conjunto gera grupos e tempos sintéticos. O cadastro associado possui campos de verificação operacional falsos e associações de estágios vazias; a aceitação geométrica não preenche essas verificações. Isso permite pesquisa sintética, mas não certifica reprodução do controle instalado.
3. **Evidência de melhoria.** Os testes de treino curtos verificam integração, não convergência. Os 2.048 passos configurados por padrão não oferecem garantia de aprendizado suficiente. Comparar políticas com a mesma demanda e sementes reservadas; repetir também treinamentos com sementes diferentes e verificar dispersão, viagens não atendidas e eventos, além da recompensa.
4. **Observação e recompensa.** O PPO recebe seis variáveis agregadas por controlador, sem observação explícita por movimento ou congestionamento a jusante. Isso limita sua capacidade de reconhecer qual aproximação precisa de verde e bloqueios entre cruzamentos. O cenário conjunto preparado tem 102 valores de observação e 120 componentes de ação. A recompensa usa espera, filas e tempo de veículos ativos, com escalas do piloto; pedestres são medidos mas não entram nela. Revisar esses pontos com experimentos controlados. A inspeção das conexões não encontrou faixas de entrada compartilhadas entre alvos neste cenário novo; manter o cuidado de deduplicação para outros mapeamentos.
5. **Cobertura de pedestres.** Há rotas em oito dos nove locais; Rondon × Belém não tem travessia cadastrada. Os testes de referência desta análise não ativaram demanda de pedestres. Contagens, geometria e atendimento precisam representar o cenário pretendido.
6. **Horizonte e validação.** Dez minutos e carga baixa comprovam execução, mas são insuficientes para caracterizar picos e estabilidade de filas. Definir aquecimento, janela de medição e tratamento de veículos ainda em viagem; conferir fluxos, filas e tempos simulados contra observações independentes antes de generalizar resultados.

## Uso recomendado

Na pasta `SistemaDeSemaforos`, abrir a interface:

```powershell
powershell -ExecutionPolicy Bypass -File .\iniciar_interface.ps1
```

Selecionar **Nove cruzamentos: cenário experimental**, preparar um cenário novo, importar e associar contagens/OD, calibrar quando forem contagens observadas e executar **Executar simulação sem treinamento**. Conferir fluxos e métricas por cruzamento. Em seguida, treinar o algoritmo e avaliar o modelo no cenário compatível, com demanda equivalente entre controles e várias sementes reservadas. Redução de fila deve ser analisada junto de espera, chegadas, viagens incompletas e atendimento dos demais acessos/pedestres.

Conclusão: infraestrutura apta aos experimentos verificados; diagnóstico de gargalos simulados disponível; melhorias no trânsito real ainda dependem de calibração, validação e comparação experimental.
