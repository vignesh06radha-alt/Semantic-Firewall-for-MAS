# Semantic Firewall for Multi-Agent Systems

The [social workflow implementation](social_mas_firewall/) runs a simulated customer-support account with three LangGraph roles. A task-scoped gateway mediates simulated reads and writes, and the semantic firewall can screen external content and inter-agent messages before the receiving role runs. The simulator uses local model endpoints and simulated accounts.

## Windows NVIDIA CUDA setup

Install Git, Python 3.12, PowerShell, an NVIDIA driver, and [Ollama for Windows](https://docs.ollama.com/windows). Run the following in PowerShell.

```powershell
git clone --branch final https://github.com/vignesh06radha-alt/Semantic-Firewall-for-MAS.git
Set-Location Semantic-Firewall-for-MAS
Set-Location social_mas_firewall
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull llama3.2:3b
ollama pull llama-guard3:8b
.\run_local_cuda.ps1 -Action Check -Guard Native
```

The native judge is Llama Guard 3 8B. The launcher records whether each model runs on the GPU or is partially offloaded. On a 6 GB GPU, `-Guard Json` uses the primary 3B model as the judge too. Its results describe a different judge configuration. The launcher starts a private Ollama process and saves logs under `social_mas_firewall/results`.

## Reproduce the fixed-scenario comparison

```powershell
.\run_local_cuda.ps1 -Action Study -Guard Json -Dataset workflow -Split development -StudyLimit 2 -StudyModes 'task_only,prompt_guard,secure,secure_boundary'
```

This smoke run takes two clean and two attack or hazard cases through each condition. `secure_boundary` retains tool permissions, provenance, the deterministic detector, and semantic review of external content. It skips the model judge on internal handoffs. Start with development, validate the selected configuration on validation, then use `-Split test -StudyLimit 0` for every held-out scenario. The workflow dataset is included as Python fixtures.

The JSON report records the scenario inventory, raw outcomes, judge profile and source hashes. The Markdown report summarizes the matched conditions. Keep judge backend, model, hardware and context fixed when comparing costs. Run the three split names independently to reproduce the entire workflow inventory.

## Evidence and paper

- [Results and evaluation methodology](social_mas_firewall/EVALUATION_REPORT.md)
- [Publication assessment and evaluation plan](social_mas_firewall/report/PUBLICATION_READINESS.md)
- [Implementation and configuration](social_mas_firewall/README.md)
- [Metric definitions and targets](social_mas_firewall/METRICS.md)
