import json
from pathlib import Path

root = Path('jobs/harbor-new200-rerun2/2026-09-05__15-13-23')
paths = []
for p in sorted(root.glob('*/result.json')):
    r = json.loads(p.read_text(encoding='utf-8'))
    reward = (((r.get('verifier_result') or {}).get('rewards') or {}).get('reward'))
    if reward != 1:
        task_path = (r.get('task_id') or {}).get('path')
        if task_path:
            paths.append(task_path.replace('\\', '/'))
paths = list(dict.fromkeys(paths))
assert len(paths) == 13, f'expected 13 non-passing tasks, got {len(paths)}'
cfg = {
    'jobs_dir': 'jobs/harbor-new200-rerun3',
    'n_concurrent_trials': 8,
    'tasks': [{'path': p} for p in paths],
    'agents': [{'name': 'oracle'}],
    'environment': {'type': 'docker', 'delete': False},
}
print(json.dumps(cfg, indent=2, ensure_ascii=False))
