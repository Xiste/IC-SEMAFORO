# Estado funcional — 07/10/2026

Esta atualização substitui as pendências de infraestrutura descritas na revisão de 06/10. Trabalho realizado na main; branch do Diego preservada.

## Complemento: fechamento do fluxo de pesquisa

Foram acrescentados gráficos ao vivo de fila, espera, chegadas e recompensa, curva de episódios completos e recuperação de acompanhamento em uma nova sessão da interface. Processos registram estado, PID e instante de criação para não confundir reutilização de PID. Cancelamento também funciona durante a inicialização e na avaliação. Recuperar o acompanhamento não reinicia um treinamento já encerrado.

`intersections.csv` mede diretamente a união das faixas por cruzamento, sem somar tabelas de controladores. `pedestrian_crossings.csv` apresenta passagens e espera nas áreas de espera das travessias indicadas na demanda. Episódios encerrados antes do horizonte são salvos com `episode_complete=false`, incluindo viagens incompletas, ações, detalhes de cruzamentos e pedestres. Em avaliações, episódios parciais ficam fora dos agregados e gráficos comparativos.

A interface importa contagens em CSV/XLSX e exige associação explícita para sensores sem ID SUMO. Converte contagens em veículos/h usando a duração das janelas e rejeita sobreposição conhecida. Importa também pares origem/destino com taxas. Há modelos de CSV para baixar. Arquivos por execução registram os dados efetivamente aplicados; contagens reais continuam responsabilidade da coleta.

O SUMO-GUI executou 120 segundos com 17 controladores, pedestres, zoom/centralização, atraso visual e captura gráfica pela API. A imagem foi inspecionada. A conexão do automatizador nativo de janelas estava indisponível, portanto cliques manuais em toolbar não foram conferidos nesta sessão; isso não impediu a execução gráfica pelo TraCI.

Pedestres podem ser ativados pela tabela de travessias. Há rotas associadas a oito dos nove locais; Rondon × Belém não tem travessia cadastrada nessa rede. O programa mostra essa cobertura e não inventa uma travessia física. Trata-se de limite do cadastro, não de falha de execução. Uma futura travessia de Belém precisa de geometria e associação informadas antes de inclusão no cenário. Os pisos atuais assumem caminhada de pelo menos 0,8 m/s.

| Pendência | Resultado |
|---|---|
| Ciclos artificiais por atendimento serial | Grupos protegidos pela matriz de conflitos SUMO; 17 controladores dos nove locais. Ciclos iniciais verificados de 67–221 s e teto de 296 s. |
| Quatro programas externos sem verde | Programas experimentais corrigidos e auditados; permanecem fixos fora do controle conjunto. |
| Contagens internas duplicando geração | Modo de calibração de rotas de borda; distingue contagem observada de novas viagens. Tolerância bloqueia ajustes inadequados. |
| Conferência do fluxo realizado | Detectores virtuais E1 e flow_counts.csv com fluxo informado, ajustado e realizado. |
| Preview incompatível com perfil | Gera a demanda original e executa somente os primeiros 30 s; preserva janelas iniciais sem tráfego. |
| Configurações avançadas em JSON | Tabelas para perfil, tipos, proporções de destinos, OD e limites das fases. |
| Progresso durante escrita | Publicação atômica de JSON e CSV de episódios; leitura tolerante na interface. |
| Instalação dependente do Anaconda | Ambiente isolado, dependências diretas e transitivas fixadas e script de abertura. |
| Testar sem algoritmo | Botão Executar simulação sem treinamento e comando run-reference. |

Os relatórios identificam o cruzamento de cada controlador e apresentam desvios padrão entre sementes nos gráficos. As métricas dos controladores não devem ser somadas indiscriminadamente quando faixas forem compartilhadas.

## Uso

Na pasta SistemaDeSemaforos, execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\iniciar_interface.ps1
```

Escolha Nove cruzamentos e Prepare e verifique. Prepare um cenário novo para obter os grupos v2; cenários seriais antigos continuam disponíveis para seus respectivos modelos. Configure a demanda, calibre quando estiver usando contagens e execute a simulação sem treinamento. Resultados podem ser exportados pela interface.

## Limites que permanecem

- As rotas ajustadas usam destinos sintéticos e um conjunto limitado de candidatos. Contagens e destinos reais continuam necessários para representar o trânsito observado.
- A demanda de pedestres agora é gerada a partir de volumes configurados; contagens reais e a cobertura física das travessias precisam ser fornecidas/verificadas. Belém continua sem travessia cadastrada.
- Programas e premissas de limpeza são experimentais; planos reais ficaram fora do escopo escolhido.
- A escolha de algoritmo, observações por movimento/jusante, recompensa, treino longo e demonstração de redução de filas continuam etapas do experimento. Testes funcionais não demonstram convergência ou melhoria de tráfego.
- Resultados parciais são preservados e identificados. Não equivalem a episódios completos e são excluídos das comparações finais.

Verificações atuais: suíte completa de 33 testes aprovada em 220,933 s, mais uma regressão de normalização de contagens parciais aprovada; 34 testes distintos verificados. AppTest conferiu recuperação em duas sessões, quatro gráficos ao vivo, curva dos episódios, cancelamento, importações, catálogos e exportação. Catálogo atualizado com 87 métricas, 462 opções SUMO e 596 consultas TraCI. SUMO-GUI executou 120 s com 17 controladores e pedestres, atraso visual e imagem inspecionada. Não executado estudo longo de otimização nem validação em campo.
