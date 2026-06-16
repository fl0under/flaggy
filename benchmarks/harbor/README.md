# Harbor integration sketch

Harbor changes quickly, so this prototype keeps the integration thin: generate a task workspace and call the installed `harbor` CLI rather than baking assumptions into the controller.

The intended shape is:

```bash
uv tool install harbor
harbor datasets list
harbor run -d "terminal-bench@2.0" -a "custom" -m "$MODEL" --n-concurrent 1
```

For your own vuln-research evals, create local Dockerized labs like `benchmarks/local-toy-web` and define validators that check the final report/evidence, not live exploitation. The useful RL data is the trajectory: plan quality, tool use, evidence discipline, false-positive rate, and clean stop points.
