"""Build a self-contained Colab notebook from the current source snapshot."""
import ast
import base64
import io
import hashlib
import json
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(part in {".venv", "__pycache__", ".git", "results"} for part in relative.parts):
                continue
            if path.name == ".env" or path.suffix in {".ipynb", ".zip", ".pyc"}:
                continue
            # Keep the snapshot portable across Windows and Linux checkouts.
            bundle.writestr(relative.as_posix(), path.read_bytes().replace(b"\r\n", b"\n"))
    encoded = base64.b64encode(archive.getvalue()).decode()
    cells = []
    def markdown(source):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": textwrap.dedent(source).strip()})
    def code(source):
        source = textwrap.dedent(source).strip()
        ast.parse(source)
        cells.append({"cell_type": "code", "metadata": {}, "source": source,
                      "execution_count": None, "outputs": []})

    markdown("""
        # Social MAS firewall — Google Colab GPU run

        This notebook contains the complete source snapshot. Run the cells in order.
        Select **Runtime → Change runtime type → T4 GPU** (or a larger GPU).
        Both Llama-Guard-3-8B and Qwen2.5-1.5B-Instruct are loaded with bitsandbytes
        NF4 4-bit quantization. The classifier uses a research policy for social
        prompt injection; it is not Meta's default safety taxonomy.

        Request model access on the [Meta model page](https://huggingface.co/meta-llama/Llama-Guard-3-8B)
        and wait for approval. Add an approved Hugging Face read token as the Colab
        secret **HF_TOKEN**. The notebook also accepts a hidden token prompt.
        Downloading the original checkpoint still transfers several GB of weights.

        The notebook starts a Transformers model service and the official A2A 0.3
        SDK gateway inside Colab. All social actions use the simulated account.
        Results identify 4-bit inference and must not be described as the reference's
        full-precision vLLM results. Colab GPU execution has not been performed when this
        notebook was generated; the validation cells record what actually happens.
    """)
    code(f'''
        import base64, io, os, pathlib, subprocess, sys, zipfile
        PROJECT = pathlib.Path('/content/social_mas_firewall')
        PROJECT.mkdir(parents=True, exist_ok=True)
        SOURCE_ARCHIVE = '{encoded}'
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(SOURCE_ARCHIVE))) as bundle:
            bundle.extractall(PROJECT)
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q',
                               '-r', str(PROJECT / 'deployment/requirements-colab.txt')])
        os.chdir(PROJECT)
        (PROJECT / 'results').mkdir(exist_ok=True)
        print('Source and dependencies ready:', PROJECT)
    ''')
    code('''
        import getpass, torch
        from huggingface_hub import hf_hub_download
        if not torch.cuda.is_available():
            raise RuntimeError('Select a GPU runtime, then rerun this cell.')
        gpu = torch.cuda.get_device_properties(0)
        print(gpu.name, round(gpu.total_memory / 2**30, 1), 'GiB')
        if gpu.total_memory < 14 * 2**30:
            raise RuntimeError('Use a Colab GPU with at least 14 GiB for both models.')
        try:
            from google.colab import userdata
            token = userdata.get('HF_TOKEN')
        except Exception:
            token = getpass.getpass('Approved Hugging Face read token: ')
        if not token:
            raise RuntimeError('A token with approved Meta model access is required.')
        os.environ['HF_TOKEN'] = token
        hf_hub_download('meta-llama/Llama-Guard-3-8B', 'tokenizer_config.json', token=token)
        os.environ.update({
            'MOCK_LLM': 'false',
            'GUARD_BACKEND': 'llama_guard_completion',
            'LLAMA_GUARD_BASE_URL': 'http://127.0.0.1:8000/v1',
            'LLAMA_GUARD_MODEL': 'meta-llama/Llama-Guard-3-8B',
            'OLLAMA_BASE_URL': 'http://127.0.0.1:8000',
            'AGENT_MODEL': 'Qwen/Qwen2.5-1.5B-Instruct',
            'AGENT_TIMEOUT_MS': '180000', 'GUARD_TIMEOUT_MS': '180000',
            'A2A_HOST': '127.0.0.1', 'A2A_PORT': '9000',
            'A2A_PUBLIC_URL': 'http://127.0.0.1:9000/',
            'COLAB_MAX_INPUT_TOKENS': '4096',
        })
        print('GPU and model access checked; live inference configured.')
    ''')
    markdown("""
        The next cell downloads and loads both models. Initial startup may take
        several minutes. If the access check fails later with 401/403, confirm the
        account behind your token has approved access to the Meta checkpoint.
        Model-service logs remain in Colab; token values are not printed.
    """)
    code('''
        import json, time, urllib.request
        def stop_process(variable):
            process = globals().get(variable)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        stop_process('a2a_process')
        stop_process('model_process')
        model_log = open(PROJECT / 'results/colab_models.log', 'w')
        model_process = subprocess.Popen([
            sys.executable, '-m', 'uvicorn', 'deployment.colab_model_server:app',
            '--host', '127.0.0.1', '--port', '8000'],
            cwd=PROJECT, env=os.environ.copy(), stdout=model_log, stderr=subprocess.STDOUT)
        def wait_ready(process, url, timeout=1200):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Service exited. Inspect its log cell below.')
                try:
                    with urllib.request.urlopen(url, timeout=3) as response:
                        return json.load(response)
                except Exception:
                    time.sleep(2)
            raise TimeoutError('Service startup timed out. Inspect the log; rerun startup after correcting it.')
        engine = wait_ready(model_process, 'http://127.0.0.1:8000/health')
        (PROJECT / 'results/colab_engine.json').write_text(json.dumps(engine, indent=2))
        print(json.dumps(engine, indent=2))
        a2a_log = open(PROJECT / 'results/colab_a2a.log', 'w')
        a2a_process = subprocess.Popen([sys.executable, '-m', 'service.a2a_server'],
            cwd=PROJECT, env=os.environ.copy(), stdout=a2a_log, stderr=subprocess.STDOUT)
        print(wait_ready(a2a_process, 'http://127.0.0.1:9000/health', timeout=60))
    ''')
    code('''
        # Live model classification + real HTTP/A2A checks, with results saved.
        subprocess.check_call([sys.executable, '-m', 'deployment.validate_live'], cwd=PROJECT)
    ''')
    markdown("""
        Run a small three-mode benchmark below. This measures real models, with a
        4-bit guard and a 4-bit Qwen primary model sharing one GPU. The same task
        prompts and simulated social tools are used in all modes. Values from the
        chemical-lab paper are not used. If the sample validation reports a false
        positive or miss, its JSON report still preserves that result.
    """)
    code('''
        subprocess.check_call([
            sys.executable, 'main.py', '--set', 'main', '--per-category', '1',
            '--modes', 'baseline,in_context,firewall', '--tag', 'colab_8b_nf4'], cwd=PROJECT)
    ''')
    code('''
        # Download results, provenance and logs from this run.
        from google.colab import files
        import shutil
        results_archive = shutil.make_archive('/content/social_mas_results', 'zip', PROJECT / 'results')
        files.download(results_archive)
    ''')
    markdown("""
        Optional diagnostics and cleanup: the diagnostic cell displays the last
        model-service log lines. The cleanup cell stops only the processes started
        by this notebook. There is no public tunnel or local-machine connection.
    """)
    code('''
        log = PROJECT / 'results/colab_models.log'
        print(log.read_text(errors='replace')[-6000:] if log.exists() else 'No model log yet.')
    ''')
    code('''
        stop_process('a2a_process')
        stop_process('model_process')
        for name in ('model_log', 'a2a_log'):
            handle = globals().get(name)
            if handle is not None:
                handle.close()
        print('Notebook services stopped.')
    ''')
    for index, cell in enumerate(cells):
        cell["id"] = hashlib.sha256(f"{index}:{cell['source']}".encode()).hexdigest()[:12]
    notebook = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
                "metadata": {"colab": {"name": "social_mas_llama_guard_8b.ipynb"},
                             "accelerator": "GPU",
                             "kernelspec": {"name": "python3", "display_name": "Python 3"},
                             "language_info": {"name": "python"}}}
    output = ROOT / "deployment/social_mas_llama_guard_8b.ipynb"
    output.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
    print(f"Built {output.name}: {len(cells)} cells, {len(archive.getvalue())} embedded source bytes")


if __name__ == "__main__":
    build()
