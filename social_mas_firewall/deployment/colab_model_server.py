"""Colab GPU server: native 8B guard completions + small agent chat model.

Transformers / bitsandbytes NF4 inference, not vLLM or full-precision 8B.
Serves the API shapes already used by the workflow; no public tunnel needed.
"""
import json
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

GUARD = os.environ.get("LLAMA_GUARD_MODEL", "meta-llama/Llama-Guard-3-8B")
AGENT = os.environ.get("AGENT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
MAX_INPUT = int(os.environ.get("COLAB_MAX_INPUT_TOKENS", "4096"))
models = {}
generation_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise RuntimeError("Select a GPU runtime in Colab before starting the server")
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    for name in (GUARD, AGENT):
        tokenizer = AutoTokenizer.from_pretrained(name)
        model = AutoModelForCausalLM.from_pretrained(name, quantization_config=quant,
                                                    device_map={"": 0}, torch_dtype=torch.float16)
        model.eval()
        models[name] = (tokenizer, model)
    yield
    models.clear()
    torch.cuda.empty_cache()


app = FastAPI(lifespan=lifespan)


def generate(name, prompt, maximum, special=False):
    import torch
    tokenizer, model = models[name]
    encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=special).to(model.device)
    count = encoded["input_ids"].shape[-1]
    if count > MAX_INPUT:
        raise HTTPException(413, "Input exceeds model-service limit; payload was not truncated")
    with generation_lock, torch.inference_mode():
        output = model.generate(**encoded, do_sample=False, max_new_tokens=maximum,
                                pad_token_id=tokenizer.eos_token_id)
    generated = output[0][count:]
    raw = tokenizer.decode(generated, skip_special_tokens=True)
    ended = int(generated[-1]) in {tokenizer.eos_token_id} if len(generated) else False
    return raw, count, len(generated), "stop" if ended or len(generated) < maximum else "length"


@app.get("/health")
async def health():
    return {"engine": "transformers", "quantization": "bitsandbytes_nf4_4bit",
            "models": {name: {"revision": getattr(model.config, "_commit_hash", None)}
                       for name, (_, model) in models.items()}}


@app.get("/v1/models")
async def available_models():
    return {"object": "list", "data": [{"id": name, "object": "model"} for name in models]}


@app.post("/v1/completions")
async def completion(body: dict):
    if body.get("model") != GUARD or not isinstance(body.get("prompt"), str):
        raise HTTPException(400, "Use the configured guard model and one string prompt")
    maximum = body.get("max_tokens", 32)
    if not isinstance(maximum, int) or not 1 <= maximum <= 128:
        raise HTTPException(400, "max_tokens must be in 1..128")
    raw, prompt_tokens, generated, finish = await run_in_threadpool(generate, GUARD, body["prompt"], maximum)
    return {"model": GUARD, "choices": [{"text": raw, "index": 0, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": generated,
                      "total_tokens": prompt_tokens + generated}}


@app.post("/api/chat")
async def chat(body: dict):
    if body.get("model") != AGENT or not isinstance(body.get("messages"), list):
        raise HTTPException(400, "Use the configured agent model and a message list")
    messages = [dict(message) for message in body["messages"]]
    schema = body.get("format")
    if isinstance(schema, dict):
        instruction = "Return only valid JSON matching this schema: " + json.dumps(schema)
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += "\n" + instruction
        else:
            messages.insert(0, {"role": "system", "content": instruction})
    tokenizer, _ = models[AGENT]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    maximum = body.get("options", {}).get("num_predict", 220)
    if not isinstance(maximum, int) or not 1 <= maximum <= 512:
        raise HTTPException(400, "num_predict must be in 1..512")
    raw, count, generated, _ = await run_in_threadpool(generate, AGENT, prompt, maximum)
    # No invented replacement if the primary model fails to emit valid JSON.
    return {"model": AGENT, "message": {"role": "assistant", "content": raw},
            "prompt_eval_count": count, "eval_count": generated, "done": True}
