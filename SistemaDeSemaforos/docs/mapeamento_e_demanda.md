# Mapeamento e demanda para os nove cruzamentos

**Atualização:** `config/mapeamento.json` contém 17 IDs candidatos da auditoria da
rede corrigida, distribuídos entre os nove cruzamentos. Eles são exibidos por
`pipeline.py mapping` e `mapping-review`, mas ainda não são alvos PPO validados.
A partir desta revisão, uma linha pode conter `controllers`, uma lista de IDs
SUMO pertencentes ao mesmo cruzamento. Cada item deve trazer seu próprio
`stage_to_phase`, `review_source`, `reconciliation_note` e as quatro marcas de
validação. Um exemplo inicial para auditoria (ainda sem estágios verificados):

```json
"controllers": [
  {"tls_id": "FAM_RONDON_PORTO_ALEGRE", "stage_to_phase": {},
   "controlled_links_verified": false, "movements_verified": false,
   "pedestrians_verified": false, "safety_verified": false,
   "review_source": "", "reconciliation_note": ""},
  {"tls_id": "3386573305", "stage_to_phase": {},
   "controlled_links_verified": false, "movements_verified": false,
   "pedestrians_verified": false, "safety_verified": false,
   "review_source": "", "reconciliation_note": ""}
]
```

`candidate_tls_ids` apenas sugere controladores. Somente IDs em `controllers`
entram na auditoria de atribuição. Os estágios de cada controlador podem ser
subconjuntos dos estágios da planilha; o conjunto do cruzamento deve cobrir todos.
Depois que os nove cruzamentos estiverem validados, `"targets_from_mapping": true`
cria um alvo PPO por controlador atribuído. Hoje essa opção continua recusada,
pois faltam a correspondência de estágios, pedestres e tempos de segurança.
A rede corrigida é selecionável por `config/cenario_rede_corrigida.json` ou pela
interface. Consulte [rede corrigida e medições](rede_corrigida_e_medicoes.md)
antes de associar as contagens a arestas SUMO. Os parágrafos abaixo descrevem
o cenário original e o processo de validação.

`config/mapeamento.json` contém os nove nomes da planilha. Apenas o ID nominal
`FAM_RONDON_PARANA` está identificado. Os outros oito IDs estão vazios. O comando
abaixo lista fases verdes, links controlados, ciclos e pendências por cruzamento:

```powershell
.\.venv\Scripts\python.exe pipeline.py mapping > resultados/mapeamento_auditoria.json
.\.venv\Scripts\python.exe pipeline.py mapping-review --output resultados/revisao_nova
```

Para validar uma linha do mapeamento, associe o nome ao `tls_id` por uma fonte
geográfica ou projeto semafórico, confira cada par `from_lane`/`to_lane` do
relatório com o movimento real e confira travessias de pedestres. Preencha
`stage_to_phase` com índices de fases verdes do programa SUMO, registre a fonte
em `review_source` e explique divergências de ciclo ou estágios em
`reconciliation_note`. Marque `controlled_links_verified`,
`movements_verified`, `pedestrians_verified` e `safety_verified` somente após
essa conferência, incluindo amarelo, limpeza e tempos mínimos e máximos. O
validador exige essas declarações e compara a quantidade de estágios, fases e
ciclo. O controle conjunto recusa alvos sem validação. A rede atual não contém
nomes de ruas utilizáveis nas arestas. O XML contém projeção UTM, mas a
conversão para latitude/longitude exige `pyproj`, ausente neste ambiente, e
uma fonte geográfica externa com os cruzamentos nomeados. Uma anotação de reconciliação
documenta a divergência; ela não transforma o programa da rede no plano da
planilha.

Esta rede veicular não contém elementos `crossing` nem `walkingArea`. Para
simular travessias de pedestres, é necessário modelá-las na rede e acrescentar
demanda de pessoas. O formato legado usa um `tls_id` por cruzamento; o campo
`controllers` descrito acima permite representar vários IDs quando houver
evidência para cada um.

Depois de preencher e validar as nove linhas, use
`"targets_from_mapping": true` no cenário. O carregador cria um alvo por
controlador atribuído, a partir de `tls_id` e `stage_to_phase`; o ambiente verifica novamente a
validação antes de iniciar o treino. Até lá, deixe essa opção ausente ou falsa.

No modo `edge_volumes`, cada linha define `from_edge` e `vehicles_per_hour`.
O total planejado por origem é `round(taxa × duração / 3600)`. `to_edge` fixa
um destino. Em vez dele, `destinations` aceita uma lista de pares
`{ "to_edge": "ID", "share": 0.7 }`, com proporções somando 1. Sem destinos,
o gerador sorteia saídas alcançáveis e registra essa hipótese sintética.
`time_profile` divide o horizonte em janelas contíguas de `begin`, `end` e
`multiplier`; os multiplicadores distribuem o total entre janelas, sem alterar
o volume total. `vehicle_types` aceita `id`, `vClass` e `share` para classes
passenger, bus, truck, delivery, motorcycle e bicycle. Os destinos informados
devem ser alcançáveis para cada classe. O arquivo `demand_manifest.json`
registra entradas, janelas, tipos e origem dos destinos. A interface expõe
esses campos JSON junto da tabela de volumes por via.

Contagens por rua precisam ainda ser vinculadas a `from_edge`, com direção,
posição da seção de contagem, horário, dia e fonte. Contagem de entrada sozinha
não determina conversões nem destinos. Use `seeds` para treino e
`evaluation.seeds` distintos para avaliação; uma demanda de avaliação pode ser
alterada no JSON sem mudar alvos, rede ou função de recompensa.
