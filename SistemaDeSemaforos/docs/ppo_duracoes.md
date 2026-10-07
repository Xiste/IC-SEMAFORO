# PPO: verde, amarelo e vermelho de limpeza

O cenário padrão usa `ppo.action_mode: phase_durations`. Cada componente da ação corresponde a uma fase de um controlador: `0` escolhe a duração mínima, `1` a duração original e `2` a máxima. No piloto `FAM_RONDON_PARANA`, são seis componentes: dois verdes, dois amarelos e dois vermelhos de limpeza. A decisão define os tempos das próximas entradas em cada fase; o tempo da fase já em andamento não é reescrito repetidamente. Fases curtas também recebem ações, mesmo quando o intervalo de decisão é de 5 s.

Limites experimentais do cenário: verde 24/41/58 s, amarelo 3/3/6 s, limpeza 1/1/3 s (mínimo/original/máximo). `duration_limits` define limites por tipo e `phase_duration_bounds` sobrescreve uma fase específica:

```json
"ppo": {
  "action_mode": "phase_durations",
  "phase_types": ["green", "yellow", "all_red"],
  "duration_limits": {
    "yellow": {"maximum_seconds": 6},
    "all_red": {"maximum_seconds": 3}
  },
  "phase_duration_bounds": {
    "FAM_RONDON_PARANA:1": {"minimum_seconds": 3, "maximum_seconds": 5}
  }
}
```

Os limites devem incluir a duração original e ser múltiplos de `step_seconds`. O mínimo do amarelo e da limpeza nunca pode ser menor que o tempo original da rede nem que o mínimo global do cenário. Limites inválidos são recusados antes de iniciar o SUMO. Esses limites não foram certificados para operação real; precisam de revisão com o projeto semafórico e a geometria.

O agente preserva a sequência e os estados dos links. O vermelho de cada aproximação depende das fases conflitantes e da limpeza; ele não é um comando independente por veículo ou movimento. O agente agora escolhe diretamente a duração da fase totalmente vermelha de limpeza.

Na interface, marque **PPO ajusta verde, amarelo e vermelho de limpeza** e configure os máximos ou os limites por fase. Use `pipeline.py ppo-train` para treinar novamente. Modelos anteriores do modo `green_extension` não são compatíveis com o novo espaço de ações. Alterar tipos de fase ou limites também exige novo treino; `ppo-eval` verifica o esquema salvo no manifesto.

`actions.csv` registra o tipo de fase, a duração total selecionada, o início da fase e o tempo restante aplicado pelo TraCI. `manifest.json` e o `run_config.json` de cada episódio registram `action_mode` e `action_spec`. O controlador de referência escolhe as durações originais; a heurística de filas mantém os tempos originais de amarelo e limpeza. `green_extension` continua disponível para reproduzir o controle antigo apenas dos verdes.

O novo modo atua nos controladores de `targets`. A ampliação aos nove cruzamentos ainda depende do mapeamento operacional validado.
