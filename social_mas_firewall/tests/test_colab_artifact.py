"""Check notebook syntax and that its embedded snapshot matches this source."""
import ast
import base64
import io
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ColabArtifactTests(unittest.TestCase):
    def test_self_contained_notebook(self):
        notebook = json.loads((ROOT / "deployment/social_mas_llama_guard_8b.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        self.assertEqual(notebook["metadata"]["accelerator"], "GPU")
        ids = set()
        embedded = None
        for cell in notebook["cells"]:
            self.assertNotIn(cell["id"], ids)
            ids.add(cell["id"])
            if cell["cell_type"] == "code":
                tree = ast.parse(cell["source"])
                self.assertEqual(cell["outputs"], [])
                for node in tree.body:
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SOURCE_ARCHIVE"
                                                            for t in node.targets):
                        embedded = ast.literal_eval(node.value)
        self.assertIsNotNone(embedded)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(embedded))) as bundle:
            for filename in bundle.namelist():
                self.assertNotIn(".venv", filename)
                self.assertNotEqual(Path(filename).name, ".env")
                self.assertEqual(bundle.read(filename), (ROOT / filename).read_bytes().replace(b"\r\n", b"\n"), filename)
            self.assertIn("service/a2a_server.py", bundle.namelist())
            self.assertIn("deployment/colab_model_server.py", bundle.namelist())
