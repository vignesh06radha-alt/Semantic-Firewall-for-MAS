"""Read-only audit of saved experiments; writes a provenance manifest beside this file."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = ['main_full', 'heldout_full', 'abl_judge_only',
        'abl_no_watch_no_egress', 'abl_no_semantic',
        'abl_sequential', 'abl_parallel_full']
manifest = {'scope': 'Saved files; no new inference performed', 'files': []}
for tag in TAGS:
    path = ROOT / 'results' / f'raw_{tag}.json'
    data = path.read_bytes()
    rows = json.loads(data)
    expected = 234 if tag == 'main_full' else 144 if tag == 'heldout_full' else 126
    assert len(rows) == expected, (tag, len(rows))
    keys = [(r['id'], r['mode']) for r in rows]
    assert len(set(keys)) == len(keys), tag
    summaries = json.loads((ROOT / 'results' / f'summary_{tag}.json').read_text())
    for mode, summary in summaries.items():
        group = [r for r in rows if r['mode'] == mode]
        attacks = [r for r in group if r['goal'] != 'none']
        assert len(group) == summary['n']
        assert len(attacks) == summary['n_attacks']
        actual = sum(r['llm_calls'] for r in attacks) / len(attacks)
        assert abs(actual - summary['avg_llm_calls_attack']) < 1e-8
    manifest['files'].append({
        'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(),
        'rows': len(rows), 'modes': dict(Counter(r['mode'] for r in rows)),
        'errors': sum(r['status'] == 'error' for r in rows),
        'max_wall_seconds': max(r['wall_ms'] for r in rows) / 1000,
    })
manifest['total_rows'] = sum(f['rows'] for f in manifest['files'])
target = Path(__file__).with_name('results_manifest.json')
target.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(f"Verified {manifest['total_rows']} rows across {len(TAGS)} files; wrote {target}")
