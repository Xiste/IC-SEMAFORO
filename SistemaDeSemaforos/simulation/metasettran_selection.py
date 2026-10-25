"""Agrupamento da seleção semanal, sem gerar viagens nem alterar seus parâmetros."""

from ..demand.metasettran_demand_generator import DAYS


def _validate_sections(selected_sections):
    if not isinstance(selected_sections, list) or not selected_sections:
        raise ValueError("Selecione ao menos uma faixa semanal em uma lista.")
    if any(type(index) is not int or not 0 <= index < 56 for index in selected_sections):
        raise ValueError("Cada faixa deve ser um inteiro entre 0 e 55.")
    if len(set(selected_sections)) != len(selected_sections):
        raise ValueError("Uma faixa não pode ser selecionada mais de uma vez.")


def section_identifiers(indices):
    """Identifica as faixas sem mudar a ordem cronológica recebida do grupo."""
    _validate_sections(indices)
    return [{"day": DAYS[index // 8], "start": f"{index % 8 * 3:02d}:00"}
            for index in indices]


def group_sections(selected_sections, group_consecutive=False):
    """Converte posições segunda 00h=0 … domingo 21h=55 em chamadas do runner.

    Grupos são ordenados pela posição inicial. A ordem interna pode atravessar
    domingo/segunda; o ciclo completo começa deterministicamente na segunda 00h.
    """
    _validate_sections(selected_sections)
    if type(group_consecutive) is not bool:
        raise ValueError("Agrupar faixas consecutivas deve ser verdadeiro ou falso.")
    selected = set(selected_sections)
    if not group_consecutive:
        groups = [[index] for index in sorted(selected)]
    elif len(selected) == 56:
        groups = [list(range(56))]
    else:
        starts = sorted(index for index in selected if (index - 1) % 56 not in selected)
        groups = []
        for start in starts:
            group = []
            index = start
            while index in selected:
                group.append(index)
                index = (index + 1) % 56
            groups.append(group)
    return [{**section_identifiers(group)[0], "sections": len(group),
             "selected_sections": group} for group in groups]
