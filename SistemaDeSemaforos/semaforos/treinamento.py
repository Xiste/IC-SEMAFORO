"""Busca de durações de fases com um modelo neural substituto."""

import json
import random

from .rede import baseline_values, phase_bounds
from .simulacao import load_scenario, simulate


def train(config, output):
    import torch

    torch.manual_seed(config["seeds"][0])
    plans, network, programs = load_scenario(config)
    base = baseline_values(config, programs)
    if not base:
        raise ValueError("Preencha targets com IDs e fases conferidos antes do treinamento")
    keys = sorted(base)
    bounds = [phase_bounds(config, programs[tls_id][int(index)])
              for tls_id, index in (key.rsplit(":", 1) for key in keys)]
    rng = random.Random(config["seeds"][0])
    samples = []
    output.mkdir(parents=True, exist_ok=False)
    model = torch.nn.Sequential(torch.nn.Linear(len(keys), 32), torch.nn.ReLU(),
                                torch.nn.Linear(32, 16), torch.nn.ReLU(), torch.nn.Linear(16, 1))

    def fit_model():
        x = torch.tensor([[s["candidate"][k] / max(1, b[1]) for k, b in zip(keys, bounds)]
                          for s in samples], dtype=torch.float32)
        y = torch.tensor([[s["mean_score"]] for s in samples], dtype=torch.float32)
        scale = y.std(unbiased=False).clamp(min=1.0)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        for _ in range(150):
            optimizer.zero_grad()
            loss = ((model(x) - y / scale) ** 2).mean()
            loss.backward()
            optimizer.step()

    def proposal():
        return {key: float(rng.randint(int(low), int(high)))
                for key, (low, high) in zip(keys, bounds)}

    for iteration in range(config["training"]["iterations"]):
        if iteration == 0:
            candidate = base
        elif iteration < config["training"]["warmup_random"]:
            candidate = proposal()
        else:
            fit_model()
            pool = [proposal() for _ in range(config["training"]["candidate_pool"])]
            with torch.no_grad():
                scores = model(torch.tensor([[p[k] / max(1, b[1]) for k, b in zip(keys, bounds)]
                                             for p in pool], dtype=torch.float32)).flatten()
            candidate = pool[int(torch.argmin(scores))]
        metrics = [simulate(config, plans, network, candidate,
                            output / f"trial_{iteration:03d}" / f"seed_{seed}", seed)
                   for seed in config["seeds"]]
        record = {"iteration": iteration, "candidate": candidate,
                  "mean_score": sum(m["score"] for m in metrics) / len(metrics),
                  "metrics": metrics}
        samples.append(record)
        with (output / "dataset.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f'Tentativa {iteration + 1}: pontuação {record["mean_score"]:.1f}', flush=True)
    best = min(samples, key=lambda sample: sample["mean_score"])
    (output / "best_candidate.json").write_text(
        json.dumps(best["candidate"], indent=2), encoding="utf-8")
    fit_model()
    torch.save(model.state_dict(), output / "surrogate_model.pt")
    print(f'Melhor pontuação: {best["mean_score"]:.1f}')
