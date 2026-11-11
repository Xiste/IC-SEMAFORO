"""Distribuicao do trafego por periodo."""
import pandas as pd
import streamlit as st


def flow_profile_editor(duration, saved=None, key='flow', planned_vehicles=0, entry_counts=None):
    import math
    from semaforos.apresentacao.estado import configuration_key
    key = configuration_key(key)
    valid = saved and abs(float(saved[-1]['end']) - duration) < .001
    profile = saved if valid else [
        {'begin': duration * i / 4, 'end': duration * (i + 1) / 4, 'multiplier': 1.}
        for i in range(4)]
    total = sum((p['end'] - p['begin']) * p['multiplier'] for p in profile)
    initial = [100 * (p['end'] - p['begin']) * p['multiplier'] / total if total else 0. for p in profile]
    scope = f'{key}_{duration}_{profile}'
    values_key = f'{scope}_shares'
    if values_key not in st.session_state:
        st.session_state[values_key] = initial
    shares = st.session_state[values_key]
    counts = [0] * len(shares)
    if all(share is not None and math.isfinite(share) and share >= 0 for share in shares) and sum(shares) > 0:
        for count in entry_counts if entry_counts is not None else [planned_vehicles]:
            allocated, cumulative = 0, 0.
            for index, share in enumerate(shares):
                cumulative += count * share / sum(shares)
                following = math.floor(cumulative + .5)
                counts[index] += following - allocated
                allocated = following
    rows = [{'period': f"{p['begin']:g} a {p['end']:g} s",
             'vehicles': count, 'share': share}
            for p, share, count in zip(profile, shares, counts)]
    st.caption('Edite a porcentagem de cada período. A quantidade estimada de veículos acompanha a proporção escolhida.')
    edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width='stretch',
        num_rows='fixed', key=f'{scope}_table_{shares}_{planned_vehicles}', disabled=['period', 'vehicles'],
        column_config={
            'period': st.column_config.TextColumn('Período da simulação'),
            'vehicles': st.column_config.NumberColumn('Veículos estimados', format='%d'),
            'share': st.column_config.NumberColumn('Porcentagem (%)', min_value=0., max_value=100., step=1., required=True)})
    updated = [float(v) if pd.notna(v) else None for v in edited['share']]
    if updated != shares:
        st.session_state[values_key] = updated
        st.rerun()
    error = None
    if any(v is None or not math.isfinite(v) or v < 0 or v > 100 for v in shares):
        error = 'Preencha uma porcentagem entre 0 e 100 em cada período.'
    elif abs(sum(shares) - 100) > .01:
        error = f'As porcentagens devem somar 100%. Total atual: {sum(shares):g}%. Ajuste os valores na tabela.'
    if error:
        st.error(error)
        result = pd.DataFrame(columns=['begin', 'end', 'multiplier'])
        result.attrs['validation_error'] = error
        return result
    st.caption('As quantidades são aproximadas e podem variar por arredondamento.')
    return pd.DataFrame([dict(p, multiplier=share / (p['end'] - p['begin']))
                         for p, share in zip(profile, shares)])
