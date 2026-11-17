"""Import split consistency and evidence integrity without network access."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datasets.import_public import normalize, record
from datasets.public_social import build_public_social


class CorpusTests(unittest.TestCase):
    def test_normalized_duplicate_and_submitter_split_are_stable(self):
        first = record("a  b", "LLMail-Inject", "revision", "one", "team", "goal")
        second = record("a b", "LLMail-Inject", "revision", "two", "team", "goal")
        third = record("different", "LLMail-Inject", "revision", "three", "team", "goal")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["split"], third["split"])

    def test_corpus_is_data_and_checksum_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.jsonl"
            item = record("untrusted input", "InjecAgent", "revision", "one", "group", "goal")
            path.write_text(json.dumps(item) + "\n", encoding="utf-8")
            manifest = path.with_suffix(".manifest.json")
            manifest.write_text(json.dumps({"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}), encoding="utf-8")
            scenarios = build_public_social(path, item["split"])
            case = next(s for s in scenarios if s["id"].startswith("public_"))
            self.assertEqual(case["platform"]["users"]["corpus_customer"]["bio"], "untrusted input")
            self.assertEqual(case["event"]["text"], "Do you have oat milk?")
            path.write_text(path.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum"):
                build_public_social(path)


if __name__ == "__main__":
    unittest.main()
