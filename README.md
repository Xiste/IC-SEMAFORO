# EDI — Executor de Demandas Integrado

O EDI gera demandas de tráfego, executa simulações no **SUMO** e organiza os resultados
para comparação de experimentos. A rede incluída representa a região Rondon Norte,
em Uberlândia. A interface web local permite configurar execuções e consultar seus outputs.

| Demanda | Aplicação |
| --- | --- |
| **Random** | Explorar a rede com origens e destinos sorteados. |
| **MetaSettran** | Estudar uma demanda experimental orientada por contagens de carros, perfis temporais e hipóteses de distribuição espacial. |

## Instalação

Este guia começa com um computador recém-formatado, conectado à internet e com
permissão para instalar programas. Escolha as instruções do seu sistema. No Linux,
o passo a passo cobre Ubuntu 22.04 ou mais recente e derivados, além do Debian 12
e 13, em computadores de 64 bits (Intel, AMD ou ARM). No Windows, as instruções
são para Windows 10/11 de 64 bits.

O EDI **não tem um instalador próprio**: seus arquivos são baixados do repositório
e a aplicação é iniciada a partir dessa pasta. Você precisará de:

- **Git** para baixar o projeto e permitir a função de apagar resultados.
- **Python 3.10 ou mais recente** para executar o EDI.
- **GNU Make** para iniciar a aplicação pelos comandos deste guia.
- **SUMO**, incluindo `sumo`, `sumo-gui`, `duarouter` e a ferramenta `randomTrips.py`.
- Um navegador de internet. No Windows, também é necessário instalar o pacote
  Python **tzdata**, usado para reconhecer o horário de Brasília.

Os testes recentes do projeto foram feitos no Linux com SUMO **1.28.0**. Versões
antigas, como a 1.18, não reconhecem a rede incluída no EDI. A versão utilizada
fica registrada nos resultados. A execução no Debian e a execução nativa no
Windows ainda precisam ser validadas.

### 1. Instale os programas necessários

Digite os comandos no terminal, um de cada vez, pressionando **Enter** e
aguardando cada um terminar antes de seguir. Quando houver uma confirmação de
instalação, responda conforme solicitado.

#### Linux — Ubuntu e Debian

Abra o aplicativo **Terminal** pelo menu de aplicativos ou pressione
**Ctrl+Alt+T**. Instale as ferramentas básicas:

```bash
sudo apt update
sudo apt install python3 python3-venv make git tzdata
```

O `sudo` pode pedir a senha da sua conta; os caracteres não aparecem enquanto
você digita. Depois, crie e ative um ambiente separado para instalar a versão
testada do SUMO. Assim você não depende das versões antigas disponíveis nos
repositórios de algumas distribuições:

```bash
python3 -m venv ~/edi-ambiente
source ~/edi-ambiente/bin/activate
python3 -m pip install eclipse-sumo==1.28.0
export SUMO_HOME="$(python3 -c 'import sumo; print(sumo.SUMO_HOME)')"
```

O pacote oficial [eclipse-sumo](https://sumo.dlr.de/docs/Downloads.php#python-packages-virtual-environments)
inclui os programas e as ferramentas do SUMO. Mantenha esse terminal aberto para
os próximos passos. Ao abrir outro terminal para executar o EDI, ative o ambiente
e defina `SUMO_HOME` novamente, como mostrado ao final da instalação.

Em outras distribuições Linux, os nomes dos pacotes podem ser diferentes.
Consulte a [instalação oficial do SUMO](https://sumo.dlr.de/docs/Installing/index.html#linux)
e instale também Git, Python 3.10+, GNU Make e os dados de fuso horário. Use o
SUMO 1.28.0 para seguir a referência testada do projeto e ajuste `SUMO_HOME` para
a pasta que contém `tools/randomTrips.py`.

#### Windows 10/11 — 64 bits

1. Abra o menu **Iniciar**, procure **PowerShell** e abra o aplicativo.
   Confira se o gerenciador de aplicativos do Windows está disponível:

   ```powershell
   winget --version
   ```

   Se o comando não for reconhecido, instale ou atualize o **Instalador de
   Aplicativo** pela Microsoft Store, feche e abra o PowerShell novamente.
   Consulte a [ajuda da Microsoft para o WinGet](https://learn.microsoft.com/pt-br/windows/package-manager/winget/)
   se precisar de ajuda.

2. Instale os quatro programas abaixo, um comando por vez. Aceite os termos
   exibidos e, se o Windows pedir, autorize a instalação. O SUMO é fixado na
   versão usada nos testes recentes do projeto.

   ```powershell
   winget install --exact --id Git.Git --source winget
   winget install --exact --id Python.Python.3.13 --source winget
   winget install --exact --id EclipseFoundation.SUMO --version 1.28.0 --source winget
   winget install --exact --id GnuWin32.Make --source winget
   ```

3. Para que o Windows encontre o Make, pesquise no menu Iniciar por **Editar as
   variáveis de ambiente da conta**. Em **Variáveis de ambiente**, selecione
   **Path**, clique em **Editar** e depois em **Novo**. Adicione o caminho abaixo
   e confirme em **OK** em todas as janelas. Se `Path` não existir, crie-o em
   **Variáveis de ambiente**.

   ```text
   C:\Program Files (x86)\GnuWin32\bin
   ```

   Caso tenha escolhido outra pasta na instalação, use o caminho da pasta `bin`
   que contém `make.exe`.

4. Feche e abra o PowerShell para carregar os novos caminhos. Instale os dados de
   fuso horário para o mesmo Python usado pelo Make:

   ```powershell
   py -3 -m pip install --user tzdata
   ```

O instalador MSI do SUMO normalmente configura `SUMO_HOME` e o caminho de seus
executáveis. Se as verificações abaixo falharem, veja a correção indicada ao
final delas.

### 2. Baixe o EDI

No mesmo terminal, escolha onde guardar o projeto. Os comandos abaixo usam a
pasta pessoal do usuário e criarão nela uma pasta chamada `edi`.

No Linux:

```bash
cd ~
```

No Windows PowerShell:

```powershell
cd $env:USERPROFILE
```

Nos dois sistemas, execute:

```text
git clone --depth 1 --single-branch --branch "Demanda-02-(Diego)" https://github.com/Xiste/IC-SEMAFORO.git edi
cd edi
```

O comando baixa os arquivos atuais do ramo `Demanda-02-(Diego)`, onde está esta
versão do EDI. A opção `--depth 1` evita baixar todo o histórico. Se a pasta `edi`
já existir, use a cópia que você já possui ou escolha outro nome no comando de
download. Nesse caso, substitua `edi` pelo nome escolhido nos comandos `cd`.

### 3. Confira a instalação

Os comandos a seguir podem ser executados de dentro da pasta `edi`. No Linux:

```bash
python3 --version
git --version
make --version
sumo --version
duarouter --version
sumo-gui --version
echo "$SUMO_HOME"
test -f "$SUMO_HOME/tools/randomTrips.py" && echo "randomTrips.py encontrado" || echo "randomTrips.py não encontrado"
python3 -c "from zoneinfo import ZoneInfo; print(ZoneInfo('America/Sao_Paulo'))"
```

No Windows PowerShell:

```powershell
py -3 --version
git --version
make --version
sumo --version
duarouter --version
sumo-gui --version
echo $env:SUMO_HOME
Test-Path "$env:SUMO_HOME\tools\randomTrips.py"
py -3 -c "from zoneinfo import ZoneInfo; print(ZoneInfo('America/Sao_Paulo'))"
```

Os programas devem mostrar suas versões, o Python deve ser 3.10 ou mais recente,
e o último comando deve mostrar `America/Sao_Paulo`. A verificação de
`randomTrips.py` deve informar que o arquivo foi encontrado no Linux ou retornar
`True` no Windows.

Se algum comando não for reconhecido, confira se a instalação correspondente
terminou e reabra o terminal. No Windows, se `SUMO_HOME` estiver vazio ou o
`Test-Path` retornar `False`, encontre no Explorador de Arquivos a pasta de
instalação do SUMO que contém `bin` e `tools`. Na janela de variáveis de
ambiente da conta, crie `SUMO_HOME` com o caminho dessa pasta e adicione
`%SUMO_HOME%\bin` ao `Path`. Confirme, reabra o PowerShell e repita as
verificações. No Linux, confira se `SUMO_HOME` aponta para a instalação correta.

### 4. Abra a interface e faça uma primeira simulação

Ainda na pasta `edi`, inicie a aplicação:

```text
make interface
```

Deixe o terminal aberto e acesse [http://127.0.0.1:8000](http://127.0.0.1:8000)
no navegador do próprio computador. Para conferir também a geração de demanda e
o SUMO:

1. Escolha o perfil de demanda **random**.
2. Defina **Duração da geração de veículos** como `60` e mantenha o intervalo
   entre partidas em `1.5`, um episódio, métricas `core` e a interface gráfica do
   SUMO desativada.
3. Clique em **Run** e aguarde **Simulação concluída**. Em **Outputs**, abra o
   resultado para consultar os arquivos gerados.

Para encerrar, volte ao terminal e pressione **Ctrl+C**. Se houver uma simulação
em andamento, mantenha o terminal aberto até ela terminar.

Para abrir o EDI novamente, abra um terminal e entre na pasta do projeto com
`cd ~/edi` no Linux ou `cd "$env:USERPROFILE\edi"` no PowerShell. No Linux,
ative o ambiente e configure o SUMO também nesse novo terminal:

```bash
source ~/edi-ambiente/bin/activate
export SUMO_HOME="$(python3 -c 'import sumo; print(sumo.SUMO_HOME)')"
```

Depois, execute `make interface`. Em outro terminal na mesma pasta,
`make kill-interface` também solicita o encerramento. No Linux, ative antes
o ambiente nesse terminal, como mostrado acima.

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
**Ctrl+C** ou `make kill-interface`, em outro terminal na mesma pasta, encerra o
atendimento web e aguarda o lote terminar, preservando a execução SUMO/SUMO-GUI
e seus resultados. Mantenha o terminal do servidor aberto até a conclusão.
Há uma instância por cópia do projeto, inclusive ao escolher outra porta.
O controle fica em `.runtime/`, ignorada pelo Git e recriada automaticamente.
A ação **Apagar resultados** faz exclusão permanente dos outputs não versionados,
com confirmação e somente quando o servidor estiver sem lote ativo, no Linux
e no Windows. Arquivos versionados e links são preservados; pastas sem permissão
de leitura não são percorridas. Falhas ao remover arquivos interrompem a operação,
e a listagem é atualizada; arquivos já removidos não são restaurados automaticamente.

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
| Porta 8000 ocupada | Inicie `make interface INTERFACE_ARGS="--port 8001"`. |
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
