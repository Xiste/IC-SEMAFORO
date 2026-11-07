# EDI — Executor de Demandas Integrado

O EDI gera demandas de tráfego, executa simulações no **SUMO** e organiza os resultados
para comparação de experimentos. A rede incluída representa a região Rondon Norte,
em Uberlândia. A interface web local permite configurar execuções e consultar seus outputs.

| Demanda | Aplicação |
| --- | --- |
| **Random** | Explorar a rede com origens e destinos sorteados. |
| **MetaSettran** | Estudar uma demanda experimental orientada por contagens de carros, perfis temporais e hipóteses de distribuição espacial. |

## Instalação

Requer **Python 3.10+**, **GNU Make** e **SUMO**, com `sumo`, `duarouter` e
`tools/randomTrips.py` disponíveis. O código de produção usa a biblioteca padrão Python.
Os ensaios recentes foram executados com SUMO **1.28.0**. A versão efetivamente usada
fica registrada em cada resultado.

Em Debian/Ubuntu, abra um terminal na raiz deste repositório e prepare o ambiente.

```bash
sudo apt-get update
sudo apt-get install python3 make sumo sumo-tools
export SUMO_HOME=/usr/share/sumo
sumo --version
make interface
```

Ajuste `SUMO_HOME` para a sua instalação e mantenha essa variável nos terminais de execução.
As instruções para outras plataformas estão na documentação oficial. [Instalação do SUMO](https://sumo.dlr.de/docs/Installing/)

## Executar pela interface

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000) com o servidor em execução.

1. Escolha **Random** ou **MetaSettran** e configure a demanda.
2. Selecione a quantidade de episódios e o perfil de métricas, `core` ou `full`.
3. Clique em **Run**. Acompanhe o estado do lote e consulte os arquivos em **Outputs**.

**Random** permite ajustar a duração da geração, o intervalo entre partidas e o
encerramento. O padrão gera partidas durante 7.200 segundos, a cada 1,5 segundo,
e aguarda o escoamento natural.

**MetaSettran** oferece uma sequência de 1–56 faixas de três horas ou uma seleção
livre na grade semanal. Na seleção livre, cada faixa é independente por padrão.
**Agrupar faixas consecutivas** une as adjacentes, inclusive de domingo para segunda.
Veículos e filas continuam dentro de cada grupo, que recebe 45 minutos finais de escoamento.
Cada episódio repete todos os grupos selecionados.

O campo **Variações por faixa** aceita um valor de 1 a 25 para cada faixa, na ordem
do resumo. Vazio, habilita o sorteio automático. Uma lista explícita repete a mesma
realização entre episódios. Os horários MetaSettran são civis de Brasília.

A opção **Exibir interface gráfica do SUMO** abre `sumo-gui` e exige sessão gráfica.
Há um lote ativo por servidor. Fechar a aba mantém o lote em execução.
**Ctrl+C** encerra o atendimento web e aguarda o lote terminar.
A ação **Apagar resultados** faz exclusão permanente dos outputs não versionados,
com confirmação e somente quando o servidor estiver sem lote ativo.

## Executar pelo terminal

```bash
# Random com os parâmetros padrão
make run-random

# Dois episódios Random com observações detalhadas
make run-random RUN_ARGS='--episodes 2 --metrics-profile full'

# MetaSettran de terça, 15h–21h, com sorteio reproduzível
python3 -B -m SistemaDeSemaforos.simulation.episode_runner \
  --demand-profile metasettran --day tuesday --start 15:00 \
  --sections 2 --master-seed 42

# Opções completas do executor
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --help
```

`make demand-random` prepara somente viagens e rotas em `SistemaDeSemaforos/demandas/`,
substituindo o par avulso anterior. Os modos de seleção, as seeds e os parâmetros
experimentais são detalhados no guia técnico. [Guia de funcionamento](docs/GUIA_DE_FUNCIONAMENTO.md)

## Consultar os resultados

Cada lote tem uma pasta exclusiva em `outputs/outputs-random/` ou
`outputs/outputs-metasettran/`. Em **Outputs**, navegue por lote e execução.

| Perfil | Conteúdo após uma execução bem-sucedida |
| --- | --- |
| `core`, padrão | Métricas globais, configurações, seeds e diagnósticos consolidados. |
| `full` | Métricas comuns, entidades em `entities.json.gz` e observações nativas em `raw/`. |

O arquivo `metrics.json` contém os indicadores com descrição e unidade. O bloco
`execution` registra condições, versão SUMO, comandos e seeds. MetaSettran conserva
`metasettran.rou.xml`. Os logs disponíveis ajudam a investigar erros. Os outputs
são locais e ficam fora do versionamento Git.

## Verificação e solução de problemas

Execute `make test` para verificar os componentes do EDI. As auditorias de manutenção
estão descritas no guia. [Verificações técnicas](docs/GUIA_DE_FUNCIONAMENTO.md#validar-e-medir-custo)

| Situação | Verificação |
| --- | --- |
| Ferramenta SUMO ausente | Confira `sumo` e `duarouter` no `PATH`, além de `$SUMO_HOME/tools/randomTrips.py`. |
| Porta 8000 ocupada | Inicie `python3 -B -m SistemaDeSemaforos.simulation.web_interface --port 8001`. |
| Falha em uma execução | Abra o lote em **Outputs** e consulte `metrics.json`, `generation.log` e `sumo.log`. |
| Janela SUMO indisponível | Confira a instalação de `sumo-gui` e a sessão gráfica. A interface web também executa com a opção gráfica desativada. |

## Escopo científico

O cenário representa carros da classe `passenger`. MetaSettran usa hipóteses de
escala regional, acessos e OD. A localização dos sensores e a interpretação UTC
dos timestamps exigem confirmação externa. As 25 variações reamostram os dados
disponíveis e têm dependência estatística.

O perfil semafórico padrão `current` usa os programas da rede. A execução dos
planos reais `settran` depende de dados operacionais complementares.
`status=completed` confirma que o processamento terminou. Para avaliar o tráfego,
consulte também chegadas, teleportes, viagens incompletas e veículos sem inserção.

Para desenvolver ou interpretar experimentos, consulte o guia e as diretrizes do projeto.
[Guia técnico](docs/GUIA_DE_FUNCIONAMENTO.md) · [Diretrizes de colaboração](docs/DIRETRIZES_COLABORACAO_IA.txt)
