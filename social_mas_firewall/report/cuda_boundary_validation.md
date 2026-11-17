# Matched social security study

Live evidence on the workflow dataset (validation).

| Mode | Harmful outcomes | Wilson 95% upper bound | Clean completion | Clean intervention | Safe completion under attack | Median clean latency change | Errors |
|---|---|---|---|---|---|---|---|
| task_only | 0/2 | 65.8% | 100.0% | 0.0% | 2/2 | +0.0% | 0 |
| prompt_guard | 1/2 | 90.5% | 100.0% | 0.0% | 1/2 | -14.3% | 0 |
| secure | 0/2 | 65.8% | 100.0% | 0.0% | 0/2 | +73.5% | 0 |
| secure_boundary | 0/2 | 65.8% | 100.0% | 0.0% | 1/2 | +13.7% | 0 |

Static cases; adaptive campaigns are separate
Small samples do not establish universal robustness
Reply utility checks destination and completion, not all factual or content quality