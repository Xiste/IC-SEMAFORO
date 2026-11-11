"""Apresentação do fluxo de trabalho, sem alterar configuração ou execução."""
import streamlit as st


def select_workflow_tab(label):
    st.session_state.ui_default_tab = label
    st.session_state.ui_next_tab = label


def workflow_navigation():
    """Navegação controlada; botões Voltar/Continuar mudam a tela visível."""
    options = ['1 · Cenário', '2 · Tráfego', '3 · Treinamento', '4 · Resultados', 'Referência técnica']
    pending = st.session_state.pop('ui_next_tab', None)
    if pending in options:
        st.session_state.ui_workflow_selection = pending
    if st.session_state.get('ui_workflow_selection') not in options:
        st.session_state.ui_workflow_selection = st.session_state.get('ui_default_tab', options[1])
    selected = st.radio('Etapas do estudo', options, horizontal=True,
                        key='ui_workflow_selection', label_visibility='collapsed')
    st.session_state.ui_default_tab = selected
    names = ['scenario', 'traffic', 'training', 'results', 'reference']
    hidden = [f'.st-key-view_{name}' for index, name in enumerate(names) if options[index] != selected]
    st.markdown('<style>' + ','.join(hidden) + '{display:none!important;}</style>', unsafe_allow_html=True)
    return tuple(st.container(key=f'view_{name}') for name in names)


def preparation_summary(rows, external_repaired=(), timings=None):
    import pandas as pd

    if timings:
        st.markdown('**Quanto tempo cada sinal fica aberto ou fechado?**')
        crossings = list(dict.fromkeys(row['cruzamento'] for row in timings))
        crossing_key = f'signal_timing_crossing_{tuple(crossings)}'
        if st.session_state.get(crossing_key) not in crossings:
            st.session_state[crossing_key] = crossings[0]
        crossing = st.selectbox('Ver tempos do cruzamento', crossings, key=crossing_key)
        local = [row for row in timings if row['cruzamento'] == crossing]
        controllers = list(dict.fromkeys(row['controlador'] for row in local))
        durations = pd.DataFrame(local)
        if len(controllers) > 1:
            durations.insert(0, 'Conjunto', durations['controlador'].map({value: f'Conjunto {index + 1}' for index, value in enumerate(controllers)}))
        durations = durations.drop(columns=[c for c in durations if c.startswith('_') or c in ('Grupo', 'cruzamento', 'controlador', 'Limpeza após amarelo (s)', 'Intervalo de segurança (s)')])
        st.dataframe(durations, hide_index=True, width='stretch', column_config={
            'Movimentos liberados': st.column_config.TextColumn(width='large', help='Entradas e movimentos compatíveis que podem receber verde juntos.'),
            'Vermelho total (s)': st.column_config.NumberColumn('Tempo de vermelho (s)', help='Tempo em que o sinal permanece vermelho durante um ciclo, enquanto outros movimentos passam e durante os intervalos de segurança.'),
        })
        st.caption('Tempos iniciais da simulação, antes do treinamento. O tempo de vermelho já inclui os intervalos de segurança. O algoritmo pode ajustar os tempos durante a execução.')


def page_header():
    from pathlib import Path
    styles = Path(__file__).with_name('interface.css').read_text(encoding='utf-8')
    st.markdown(f'<style>{styles}</style>', unsafe_allow_html=True)
    st.markdown('''<div class="lab-hero">
      <span class="lab-eyebrow">Rondon Norte / Pesquisa em mobilidade</span>
      <h1>Laboratório de trânsito</h1>
      <p>Da configuração ao resultado: simule o tráfego e descubra como o aprendizado pode ajustar os semáforos.</p>
      <div class="lab-tags"><span>Uberlândia, MG</span><span>9 cruzamentos disponíveis</span><span>Ambiente experimental</span></div>
    </div>''', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('<div class="lab-section">Seu percurso</div>', unsafe_allow_html=True)
        st.subheader('Seu estudo de trânsito')
        st.markdown('''<div class="guide-item"><span class="guide-number">01</span><div><strong>Conheça a rede</strong><small>Nove cruzamentos controlados em conjunto.</small></div></div>
        <div class="guide-item"><span class="guide-number">02</span><div><strong>Configure pelo mapa</strong><small>Semáforos, vias e travessias.</small></div></div>
        <div class="guide-item"><span class="guide-number">03</span><div><strong>Treine os semáforos</strong><small>Escolha um objetivo e inicie.</small></div></div>
        <div class="guide-item"><span class="guide-number">04</span><div><strong>Compare o resultado</strong><small>Confira espera, viagens e atendimento.</small></div></div>''', unsafe_allow_html=True)
        with st.expander('Primeira vez por aqui?'):
            st.markdown('1. Localize as vias no mapa da rede.\n\n2. Informe os veículos por hora e os segundos de simulação.\n\n3. Use **Teste de funcionamento** no primeiro treino.\n\n4. Ao terminar, clique em **Comparar este modelo com os tempos iniciais**.')
            st.caption('Tempo simulado é o tempo de trânsito representado. O tempo no computador depende da execução.')
        st.divider()


def step_heading(number, title, description):
    from html import escape
    st.markdown(f'<div class="step-heading"><span class="step-badge">{number:02d}</span><h3>{escape(title)}</h3></div>', unsafe_allow_html=True)
    st.caption(description)


def section_label(text):
    from html import escape
    st.markdown(f'<div class="lab-section">{escape(text)}</div>', unsafe_allow_html=True)


def configuration_guidance(error):
    """Liga a validação técnica a uma ação e uma etapa compreensíveis."""
    text = (error or '').casefold()
    if any(term in text for term in ('prepare', 'rede válida', 'travessias')):
        return '1 · Cenário', 'Confira a rede dos nove cruzamentos e clique em Preparar simulação se for necessário carregá-la novamente.'
    if any(term in text for term in ('medição', 'measurement', 'aquecimento', 'warmup', 'janela', 'start_seconds', 'end_seconds')):
        return '2 · Tráfego', 'Confira a duração e o aquecimento na aba Tráfego. O aquecimento precisa terminar antes do fim da simulação.'
    if any(term in text for term in ('veículo', 'entrada', 'pessoas', 'pedestre', 'fluxo', 'intervalo temporal', 'perfil', 'porcentag', 'volume', 'tráfego')):
        return '2 · Tráfego', 'Confira os volumes, a duração e os percursos ativados. Preencha uma quantidade suficiente para gerar participantes na simulação.'
    if any(term in text for term in ('limites', 'mínimo', 'maximum_cycle', 'phase_duration')):
        return '2 · Tráfego', 'No mapa, selecione Semáforos e confira os limites de verde do cruzamento.'
    return '3 · Treinamento', 'Confira os ajustes avançados e os limites dos semáforos. Os limites precisam incluir o tempo inicial e respeitar os mínimos do cenário.'


def friendly_configuration_error(error):
    """Mantém o detalhe técnico nos arquivos, com uma ação clara na tela."""
    text = str(error or '')
    lowered = text.casefold()
    if 'porcentag' in lowered:
        return text
    if any(t in lowered for t in ('pessoas/h', 'ao menos um pedestre', 'zero pedestres')):
        return 'Em Tráfego, preencha pessoas por hora em pelo menos uma travessia ou desative a opção de incluir pedestres. Para gerar pessoas, pode ser necessário aumentar o volume ou a duração.'
    if 'step_seconds' in lowered and ('duraç' in lowered or 'múltipl' in lowered):
        return 'O passo da simulação não combina com os tempos dos semáforos. Em Tráfego → Avançado, use 1 segundo ou um valor que divida esses tempos exatamente.'
    if 'decision_seconds' in lowered:
        return 'O intervalo entre decisões precisa ser igual ou maior que o passo da simulação. Confira esses dois valores nos ajustes avançados.'
    if any(t in lowered for t in ('measurement', 'warmup', 'medição', 'aquecimento', '0 ≤')):
        return 'O aquecimento precisa terminar antes do fim da simulação. Ajuste a duração ou reduza o aquecimento na aba Tráfego.'
    if any(t in lowered for t in ('limites ppo', 'mínimo', 'máximo de ciclo', 'phase_duration', 'maximum_cycle')):
        return 'Em Tráfego → mapa → Semáforos, confira os verdes: o mínimo não pode superar o máximo, os limites devem incluir o tempo inicial e respeitar os tempos de segurança.'
    if any(t in lowered for t in ('n_steps', 'batch_size', 'minibatch', 'parâmetros ppo')):
        return 'Nos ajustes avançados do treinamento, a coleta precisa ser múltipla do tamanho do lote, e o lote não pode ser maior que a coleta.'
    if 'semente' in lowered:
        return 'Use números inteiros diferentes para as sementes de treino e avaliação, separados por vírgulas no campo de avaliação.'
    if any(t in lowered for t in ('sumo não encontrado', 'sumo nao encontrado')):
        return 'O simulador não foi encontrado. Confira a instalação do SUMO e sua configuração no computador.'
    if isinstance(error, (ValueError, TypeError)) and ('invalid literal' in lowered or 'could not convert' in lowered):
        return 'Confira os campos numéricos: preencha somente números válidos, sem letras ou campos vazios.'
    if 'prepare' in lowered or 'rede válida' in lowered:
        return 'Na aba Cenário, confira a rede dos nove cruzamentos e clique em Preparar simulação antes de continuar.'
    if any(t in lowered for t in ('zero veículos', 'gerar tráfego', 'veículos por hora')):
        return 'Em Tráfego, preencha o volume de pelo menos uma entrada. Se os valores forem baixos, aumente o volume ou a duração para gerar veículos.'
    return text or 'Confira os valores preenchidos antes de iniciar.'


def readiness_panel(config, error, busy=False):
    with st.sidebar:
        section_label('Antes de executar')
        if st.session_state.get('ui_default_tab') == '2 · Tráfego':
            st.caption('Configure as vias no mapa. Os ajustes são conferidos ao avançar para o treinamento ou executar uma simulação.')
        elif config is None:
            destination, instruction = configuration_guidance(error)
            st.warning(f'Falta um ajuste em {destination}.')
            st.caption(instruction)
        else:
            st.success('Configuração pronta')
            st.caption(f"{len({t['name'] for t in config['targets']})} cruzamento(s) · {config['duration_seconds']:g} s por simulação")
        if busy:
            st.info('Há uma execução em andamento. Acompanhe ou interrompa na etapa 4.')
        st.caption('Alterar os campos configura a próxima execução. Um processo em andamento mantém a configuração com que foi iniciado.')


def configuration_summary(config, error=None):
    st.subheader('Confira antes de executar')
    if config is None:
        st.error(f'A configuração precisa de um ajuste: {error}')
        destination, instruction = configuration_guidance(error)
        st.caption(instruction)
        st.button(f'Conferir ajustes em {destination}', on_click=select_workflow_tab, args=(destination,), key='fix_configuration')
        return
    count = len({target['name'] for target in config['targets']})
    window = config['measurement']
    algorithm = config.get('algorithm', 'PPO')
    from semaforos.algoritmos.registro import get_algorithm
    budget = config.get(get_algorithm(algorithm).config_key, {}).get('total_timesteps', 2048)
    traffic = config['demand']
    if traffic['mode'] == 'random':
        traffic_description = f"{traffic['vehicles_per_hour']:g} veículos por hora na rede"
    elif traffic['mode'] == 'edge_volumes':
        traffic_description = f"{sum(row['vehicles_per_hour'] for row in traffic['edge_volumes']):g} veículos por hora nas entradas informadas"
    elif traffic['mode'] == 'flows':
        traffic_description = 'viagens entre as origens e os destinos informados'
    else:
        traffic_description = 'tráfego ajustado às contagens reais'
    objectives = config.get('objectives', {})
    objective = next((name for name, weights in {
        'Equilibrar os resultados': {'waiting': 1., 'queues': 1., 'travel': 1.},
        'Diminuir a espera': {'waiting': 2., 'queues': 1., 'travel': 1.},
        'Diminuir as filas': {'waiting': 1., 'queues': 2., 'travel': 1.},
    }.items() if objectives == weights), 'Prioridades personalizadas')
    st.info(f"Você vai treinar o {algorithm} em {count} cruzamento(s), com {traffic_description}. Objetivo: {objective.lower()}.")
    columns = st.columns(4)
    columns[0].metric('Cruzamentos no estudo', count)
    columns[1].metric('Duração de cada simulação', f"{config['duration_seconds']:g} s")
    columns[2].metric('Tempo de medição', f"{window['end_seconds'] - window['start_seconds']:g} s")
    columns[3].metric('Decisões solicitadas para treinar', f'{budget:,}'.replace(',', '.'))
    st.caption('O algoritmo repete simulações para praticar. A duração de cada simulação é tempo de trânsito; a quantidade de decisões define o treinamento. O tempo no computador depende da execução.')
    modes = {'random': 'Taxa total da rede', 'edge_volumes': 'Entradas por via',
             'observed_counts': 'Contagens observadas com calibração', 'flows': 'Origens e destinos'}
    with st.expander('Detalhes do período de medição'):
        st.caption(f"{modes[config['demand']['mode']]} · Aquecimento: {window['warmup_seconds']:g} s · Medição: {window['start_seconds']:g}–{window['end_seconds']:g} s")
    if config['demand']['mode'] == 'observed_counts':
        st.info('Antes do treino, confira o ajuste em Tráfego e valide as passagens no SUMO. O ajuste das rotas, sozinho, não comprova calibração.')
