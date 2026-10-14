"""GPU validation must distinguish real residency from CPU fallback."""
import os
os.environ["MOCK_LLM"] = "true"

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import settings
from deployment.local_cuda import check_cuda
from firewall.guardian_llm import JudgeResult
from llm.client import LLMResult


class CudaEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def probe(self, vram):
        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}, {"name": "llama-guard3:8b"}]})
            return httpx.Response(200, json={"models": [
                {"name": "llama3.2:3b", "size": 100, "size_vram": vram},
                {"name": "llama-guard3:8b", "size": 100, "size_vram": vram}]})
        client_class = httpx.AsyncClient
        def client(**kwargs):
            return client_class(transport=httpx.MockTransport(handler), **kwargs)
        saved = []
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "runtime.log"
            # Device discovery alone is insufficient if the model stayed on CPU.
            log.write_text("inference compute library=CUDA", encoding="utf-8")
            with patch.object(settings, "MOCK_LLM", False), patch.object(settings, "GUARD_BACKEND", "llama_guard_ollama"), \
                 patch("deployment.local_cuda.httpx.AsyncClient", side_effect=client), \
                 patch("deployment.local_cuda.subprocess.run", return_value=SimpleNamespace(stdout="RTX 4050, 592.82, 6141, 5920")), \
                 patch("deployment.local_cuda.chat_json", return_value=LLMResult({"ok": True})), \
                 patch("deployment.local_cuda.judge", side_effect=[JudgeResult("safe", "none", "", False, 0, 0),
                                                                 JudgeResult("unsafe", "rule_override", "", False, 0, 0)]), \
                 patch("deployment.local_cuda.save_report", side_effect=lambda name, report: saved.append(json.loads(json.dumps(report)))):
                if vram == 0:
                    with self.assertRaisesRegex(RuntimeError, "CUDA was not verified"):
                        await check_cuda(str(log))
                else:
                    await check_cuda(str(log))
        return saved[-1]

    async def test_cpu_fallback_is_not_reported_as_cuda(self):
        report = await self.probe(0)
        self.assertFalse(report["cuda_verified"])
        self.assertEqual(report["residency"][0]["placement"], "CPU")

    async def test_partial_gpu_offload_is_recorded_explicitly(self):
        report = await self.probe(50)
        self.assertTrue(report["cuda_verified"])
        self.assertEqual(report["residency"][0]["placement"], "CPU + GPU")


if __name__ == "__main__":
    unittest.main()
