# Estado funcional — 07/10/2026

Esta atualização substitui as pendências de infraestrutura descritas na revisão de 06/10. Trabalho realizado na main; branch do Diego preservada.

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
- As travessias têm estágios e pisos geométricos, mas não existe geração de demanda real de pedestres.
- Programas e premissas de limpeza são experimentais; planos reais ficaram fora do escopo escolhido.
- A escolha de algoritmo, observações por movimento/jusante, recompensa, treino longo e demonstração de redução de filas continuam etapas do experimento. Testes funcionais não demonstram convergência ou melhoria de tráfego.
- Resultados parciais de treinamento não equivalem a episódios completos; a tabela de episódios conserva somente os concluídos.

Verificações: instalação isolada e pip check aprovados; suíte de 27 testes aprovada e teste adicional de rejeição de contagens incompatíveis aprovado. AppTest verificou os nove cruzamentos, formulários, catálogos e exportação. Não executado estudo longo de otimização nem validação em campo.
