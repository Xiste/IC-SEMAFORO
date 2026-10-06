# Rede corrigida, auditoria e contagens locais

Estes arquivos foram copiados de `origin/Demanda-01-(Diego)`, commit `242f703`, para a `main`. A branch de origem não foi modificada. A rede corrigida fica em `dados/rede/uberlandia.rondon_norte_corrigida.net.xml`; o cenário original continua em `config/cenario.json` e a rede corrigida pode ser escolhida com `config/cenario_rede_corrigida.json` ou na interface.

```powershell
cd SistemaDeSemaforos
.\.venv\Scripts\python.exe pipeline.py inspect --config config/cenario_rede_corrigida.json
.\.venv\Scripts\python.exe pipeline.py mapping --config config/cenario_rede_corrigida.json
.\.venv\Scripts\python.exe pipeline.py mapping-review --config config/cenario_rede_corrigida.json --output resultados/revisao_corrigida
.\.venv\Scripts\python.exe pipeline.py run --config config/cenario_rede_corrigida.json
.\.venv\Scripts\python.exe pipeline.py measurements
```

A rede corrigida tem 36 programas semafóricos, 43 arestas `crossing` e 75 `walkingarea`. O arquivo `dados/auditoria/current_tls_audit.csv` associa 17 IDs SUMO como **candidatos** aos nove cruzamentos da planilha. `config/mapeamento.json` registra esses candidatos, e `mapping` mostra os estados físicos, de pedestres e de associação com a SETTRAN. A cor amarela no mapa de revisão indica candidato; verde indica ID já preenchido no mapeamento; vermelho indica outro controlador. Nenhum dos nove está plenamente validado para controle conjunto. Os arquivos `settran_audit.csv` e `settran_programs.json` preservam a auditoria e os 36 planos extraídos; os planos ainda não estão convertidos em fases SUMO executáveis.

`dados/medicoes/Medicoes_5_6.csv` contém 175.729 observações dos detectores `vlink_id` 5 e 6. `measurements` mostra os rótulos, a cobertura, as durações das janelas e taxas em veículos/h calculadas **somente para janelas observadas de exatamente 60 s**. Essas taxas não representam uma hora contínua nem a demanda da rede. Não há coordenadas, direção comprovada, fuso horário ou associação dos IDs `vlink` com arestas SUMO. `vehicle_total` usa a convenção da fonte; motocicletas, bicicletas e pessoas aparecem separadamente. Não preencha `edge_volumes` a partir dessas duas linhas antes de validar a localização e a seção de contagem.

Uma execução curta com a rede corrigida iniciou SUMO/TraCI e completou 20 s simulados. SUMO emitiu avisos `Missing green phase` para índices de vários programas, inclusive controladores ligados aos nove cruzamentos. A rede acrescenta infraestrutura física, mas ainda precisa de revisão dos programas, travessias e tempos de segurança antes de servir como referência operacional. Modelos PPO treinados na rede original devem ser treinados novamente para a rede corrigida; a avaliação já confere o hash da rede do modelo.

SHA-256 da rede corrigida: `f30b0807fa46e3d4fb65c573be68f6544d75a64e44a2c32fee71389fd4106d56`.

SHA-256 das contagens: `17a0a903419733731515f9c9dd49e84623964d6f03aa0c43594ed68be5c23c9c`.
