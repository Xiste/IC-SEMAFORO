# Cadastro dos nove cruzamentos

Preparado em 06/10/2026 na main com a geometria aceita pelo usuário e os 17 IDs do inventário geográfico. Associação baseada no inventário existente e na conferência visual, sem atribuição de grupos reais por suposição.

| Etapa | Resultado atual | Continuação |
| --- | --- | --- |
| Associar cruzamentos/controladores | Nove cruzamentos, 17 controladores distintos no mapeamento associado. | Confirmar a identidade operacional dos focos/grupos. |
| Extrair faixas e movimentos | 150 conexões, 31 de pedestres; entrada, saída, direção e estados por fase. | Associar os grupos reais aos índices de links. |
| Preparar estágios e tempos | 32 estágios do plano 4 extraídos da auditoria da planilha, com descrições e tempos. | Identificar os links liberados por estágio, sequência completa e referência da defasagem. |
| Programas desligados e travessias | Seis controladores com estados desligados; atendimento de cada conexão registrado. | Gerar programas após resolver a correspondência e os conflitos, incluindo pedestres. |
| Treino conjunto | Estrutura do projeto já aceita múltiplos alvos. | Requer programas executáveis e mapeamento operacional completo; treino dos nove não executado nesta etapa. |

## Arquivos para conferir

- [Controladores por cruzamento](../dados/auditoria/cadastro_nove/controladores.csv).
- [Faixas e movimentos](../dados/auditoria/cadastro_nove/movimentos.csv): `grupo_real`, `estágio_real` e `evidência_operacional` aguardam preenchimento. A conversão geométrica é extraída de `connection.dir`, não de vistoria de campo.
- [Estágios e tempos do plano 4](../dados/auditoria/cadastro_nove/estagios_a_associar.csv): preencher `tls_ids_confirmados`, `link_indices_confirmados` e `evidência` por estágio.
- [Estado de cada movimento em cada fase](../dados/auditoria/cadastro_nove/fases_por_movimento.csv).
- [Mapeamento associado](../config/mapeamento_associado.json): `controllers` preenchidos, `stage_to_phase` e marcas operacionais continuam aguardando conferência.
- [Auditoria operacional](../dados/auditoria/cadastro_nove/auditoria_operacional.json): pendências por controlador; 0/9 operacionais neste estágio.

A tabela de estágios é uma ficha de conferência, não um arquivo de configuração SUMO. Os números de links só têm significado junto com seu `tls_id`; um link pode representar mais de uma conexão, todas devem ser verificadas. Os programas atuais não são equivalentes automaticamente aos planos da planilha. Vermelho residual de uma aproximação não é uma fase adicional para concatenar no ciclo.

## Como concluir

1. Conferir `movimentos.csv` com o cadastro operacional/projeto e identificar os links de cada grupo real.
2. Para cada estágio da planilha, registrar os grupos e movimentos que recebem verde. Registrar também os movimentos de pedestres e transições.
3. Gerar as fases SUMO a partir dessas associações e tempos; conferir conflitos, ciclo, atendimento de todas as conexões e sincronização dos controladores do mesmo cruzamento.
4. Preencher `stage_to_phase` do mapeamento associado com os índices das fases verdes geradas. Marcar as verificações e fontes somente com a conferência concluída.
5. Em um cenário dedicado, usar a rede com esses programas, apontar `mapping_path` para `mapeamento_associado.json` e auditar com `pipeline.py mapping`. Ao obter 9/9, habilitar `targets_from_mapping` e treinar/avaliar com cenários e sementes independentes.

Uma alternativa para pesquisa é gerar programas experimentais a partir da rede com SUMO. Isso requer identificar o cenário e seus tempos como sintéticos; não reproduz automaticamente os planos reais. A escolha entre reprodução real e cenário experimental foi apresentada ao usuário nesta etapa e aguarda resposta.

O cadastro foi produzido com:

```powershell
.\.venv\Scripts\python.exe scripts\preparar_cadastro_nove.py
```

O script verifica hashes da rede e da planilha, unicidade dos controladores e existência de todas as conexões. Ele recusa sobrescrever um cadastro existente para preservar o preenchimento manual. O cenário ativo e os programas da rede não são alterados pela extração.
