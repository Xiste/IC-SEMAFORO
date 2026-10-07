# Interface e tabelas do pipeline

## Legendas em português e exportação CSV

Os campos da interface têm ajuda em português. As tabelas de parâmetros e métricas incluem `nome em português` e `legenda em português`, preservando os códigos técnicos. As 27 categorias SUMO têm nomes em português e uma legenda de tipos; descrições originais da instalação SUMO/TraCI permanecem disponíveis como referência técnica.

As tabelas de avaliação, estatísticas agregadas, resultados por controlador e episódios de treino mostram títulos e unidades em português, com explicação ao passar o mouse no cabeçalho. Em cada tabela de resultado há:

- **Exportar métricas em português (.csv)**: títulos legíveis, unidades e código técnico entre parênteses; valores preservados.
- **Legenda em português → Exportar legenda das colunas (.csv)**: significado, unidade e código de cada coluna.
- Exportação original com os nomes técnicos para uso em scripts.

Isso também funciona em **Abrir relatórios de execuções anteriores**. CSVs em português usam UTF-8 com BOM para preservar acentos ao abrir em aplicativos Windows. O separador é vírgula. Em caso de configuração regional diferente no Excel, importe o arquivo selecionando UTF-8 e vírgula. Célula vazia significa valor ausente, não zero; viagens sem chegada ficam fora das estatísticas de duração. Gráficos de novas avaliações usam títulos das métricas em português; imagens de execuções antigas preservam seus títulos anteriores.

| Requisito | Implementação atual | Conferência e limite |
| --- | --- | --- |
| 2. Carregar configurações-base e listar opções | Campos de rede, demanda, passo, horizonte, sementes, objetivos, PPO e coleta. Aba com todas as 462 opções CLI SUMO 1.27.1, 27 categorias, busca e download. | Catálogo obtido do executável instalado; não significa que as 462 opções sejam editáveis pela interface. |
| 3. Executar e conferir dez épocas e parâmetros | PPO com n_epochs=10; tabela de cada campo do cenário, fases/ações derivadas, todos os argumentos do construtor SB3 e comando SUMO. Previsão de coletas, passos, minibatches e episódios. | Dez épocas são passagens por coleta, não dez episódios. Medição local em dados/auditoria/benchmark_ppo_10_epocas.json. Não demonstra convergência. |
| 4. Relatório e métricas disponíveis | Relatórios por execução/alvo, média e dispersão por controlador, gráficos, viagens, filas, emissões, eventos, recursos e ações. Catálogo completo de 596 consultas públicas get dos domínios TraCI instalados. | Catálogo da API distingue disponibilidade de coleta. Pedestres/detectores exigem infraestrutura no cenário. Viagens incompletas não entram nas estatísticas de viagem. |

## Tabelas completas

- [Todas as opções CLI SUMO](catalogos/sumo_options.csv): categoria, opção, tipo, padrão no template, aliases e descrição original.
- [Todos os parâmetros atuais](catalogos/effective_parameters.csv): cenário padrão, construtor PPO, programas dos alvos, ações e comando.
- [Métricas coletadas](catalogos/metrics_catalog.csv): unidade, escopo, fonte e estado da coleta.
- [Todas as consultas TraCI](catalogos/traci_queries.csv): domínio, método, assinatura e documentação local.
- [Escopo, versão e orçamento](catalogos/catalog_scope.json).

As tabelas CSV documentais correspondem ao cenário padrão. Na interface, parâmetros e coleta refletem os campos atuais. Treino e avaliação também exportam esses quatro CSVs na própria pasta do resultado. `run_config.json` conserva comando e semente por episódio; `manifest.json` conserva configurações, versões e hashes. Valores padrão do template SUMO não substituem esses registros. Atributos XML de redes, vType e modelos e outras ferramentas SUMO não pertencem ao catálogo CLI do executável `sumo`.

O treino grava `training_episodes.csv` com os episódios concluídos, contadores, recompensa e estatísticas de tripinfo. Pode terminar no meio de um episódio, que não entra nessa tabela. `tripinfo.xml` permanece por episódio. A avaliação grava `runs.csv`, `signals.csv`, `aggregate.csv`, `summary.json`, `report.md` e `comparison.png`. Os campos training.iterations/warmup_random/candidate_pool pertencem à busca legada e não determinam o treino PPO. plans/plan_id servem à planilha/auditoria e não substituem os programas semafóricos da rede.

Métricas adicionais: parados globais em veículo·s e pico global, CO/HC/NOx/PMx em gramas e consumo elétrico positivo em Wh; são integradas no horizonte observado, e não por rota completa. CO₂ e combustível também dependem do modelo de emissão. Para cada atributo de viagem concluída há média, p95, desvio populacional, mínimo, máximo e mediana. A dispersão entre execuções em aggregate.csv usa desvio amostral.

## Abrir a interface (PowerShell)

```powershell
cd C:\Projetos\IC-SEMAFORO\SistemaDeSemaforos
.\.venv\Scripts\python.exe -m streamlit run interface.py
```

Acesse http://localhost:8501. As três abas estão abaixo dos campos do cenário. Há consulta visual dos nove locais, acompanhamento do treino, downloads e abertura de resultados anteriores. A opção SUMO-GUI abre a janela do simulador durante o trabalho.

Para atualizar os CSVs documentais após mudar SUMO ou o cenário:

```powershell
.\.venv\Scripts\python.exe scripts\exportar_catalogos.py
```

O script de benchmark executa 2.048 passos, dez épocas, um controlador, horizonte 600 s, demanda sintética 360 veículos/h, sem GUI e com emissões. Depois avalia três controladores em uma semente independente. Esse ensaio verifica custo e funcionamento, não superioridade. O diretório de resultado precisa ser novo; o script não sobrescreve experimentos existentes.

Resultado medido em 06/10/2026: **204,99 s (3 min 25 s), 17 episódios completos, 16 coletas e 320 atualizações de gradiente previstas**. Houve testes concorrentes durante parte do treino; não é uma medição isolada. A avaliação em semente 101 produziu três execuções com 60 veículos planejados cada. É um orçamento computacional viável para este piloto; não mede o custo dos nove cruzamentos, da GUI ou de demanda mais intensa e não estabelece convergência ou superioridade do PPO.
