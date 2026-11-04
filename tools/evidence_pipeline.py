"""Build and execute reusable case pipelines using existing strict validators.

Config commands are trusted developer-authored argv arrays. A render check returns
0 for verified reusable output, 10 for missing safe-to-create output, otherwise
failure. Review checks return 75 when actual inspection is still required.
"""
import argparse
import html
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.artifact_store import atomic_json, digest
from tools.storage_policy import confined, enforce
from tools.evidence_job import check_argv, load_plan


def config(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    required = {'schema_version', 'preflight_argv', 'numeric_gate_argv', 'verify_argv',
                'review_check_argv', 'storage_argv', 'review_directory', 'cases'}
    if set(value) != required or value['schema_version'] != 1:
        raise ValueError('Invalid pipeline configuration')
    for field in required - {'schema_version', 'review_directory', 'cases'}:
        check_argv(value[field])
    confined(ROOT / value['review_directory'])
    seen = set()
    if not 1 <= len(value['cases']) <= 250:
        raise ValueError('Use bounded batches of 1..250 cases')
    for case in value['cases']:
        if set(case) != {'id', 'directory', 'check_argv', 'render_argv', 'timeout_s'} or case['id'] in seen:
            raise ValueError('Invalid or duplicate case')
        seen.add(case['id'])
        confined(ROOT / case['directory'])
        check_argv(case['check_argv'])
        check_argv(case['render_argv'])
    return value


def command(argv):
    return subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL, check=False,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).returncode


def run_case(value, case_id):
    case = next(c for c in value['cases'] if c['id'] == case_id)
    code = command(case['check_argv'])
    if code == 0:
        print('EVIDENCE_RESULT ' + json.dumps({'case_id': case_id, 'reused': True}), flush=True)
        return 0
    if code != 10:
        raise RuntimeError(f'Case {case_id} has stale/invalid evidence; reconcile before rendering (check={code})')
    code = command(case['render_argv'])
    if code:
        return code
    code = command(case['check_argv'])
    if code:
        raise RuntimeError(f'Case {case_id} did not pass post-render verification ({code})')
    print('EVIDENCE_RESULT ' + json.dumps({'case_id': case_id, 'reused': False}), flush=True)
    return 0


def review_index(value):
    """Index existing full-motion sheets/movies; never invent an inspection."""
    from tools.artifact_bundle import validate_manifest
    from tools.artifact_store import files_complete
    output = confined(ROOT / value['review_directory'])
    enforce(output, growth=1024**2)
    rows = []
    for case in value['cases']:
        directory = confined(ROOT / case['directory'])
        manifest, _, motion = validate_manifest(directory)
        if not manifest.get('complete') or not files_complete(directory, manifest):
            raise RuntimeError('Incomplete media: ' + case['id'])
        views = []
        for label, view in manifest['views'].items():
            sheet = confined(directory / (label + '-sheet.png'))
            media = view.get('media')
            movie = confined(directory / media['path']) if media else None
            views.append({'view': label, 'sheet': str(sheet), 'sheet_sha256': digest(sheet),
                          'movie': str(movie) if movie else None,
                          'representation': view.get('sheet_representation', {'kind': 'full_sheet'}),
                          'frames': len(manifest['expected_frames'])})
        rows.append({'case_id': case['id'], 'motion_sha256': digest(motion), 'views': views})
    output.mkdir(parents=True, exist_ok=True)
    # Original-resolution sheets are embedded, not rerendered or resampled.
    pages = []
    for number, start in enumerate(range(0, len(rows), 8)):
        page = output / f'review-{number:03d}.html'
        body = ['<!doctype html><meta charset="utf-8"><title>Evidence review</title>',
                '<h1>Review required</h1><p>This index does not record inspection. ',
                'Selected-frame sheets do not replace full-motion review; open the retained movie.</p>']
        for row in rows[start:start + 8]:
            body.append('<h2>' + html.escape(row['case_id']) + '</h2>')
            for view in row['views']:
                body.append('<p>' + html.escape(view['view'] + ': ' + view['representation']['kind']) + '</p>')
                if view['movie']:
                    body.append('<a href="' + html.escape(Path(view['movie']).as_uri()) + '">Full-motion movie</a>')
                body.append('<div style="overflow:auto"><img alt="Saved motion sheet" src="' +
                            html.escape(Path(view['sheet']).as_uri()) + '"></div>')
        text = '\n'.join(body)
        if not page.exists() or page.read_text(encoding='utf-8') != text:
            page.write_text(text, encoding='utf-8')
        pages.append(str(page))
    index = output / 'review-index.json'
    atomic_json(index, {'schema_version': 1, 'inspection_claimed': False, 'cases': rows, 'pages': pages})
    print('EVIDENCE_RESULT ' + json.dumps({'review_index': str(index), 'case_count': len(rows)}))


def build(path, destination):
    value = config(path)
    path = str(Path(path).resolve())
    config_hash = digest(path)
    steps = []
    def add(name, phase, argv, timeout=3600, **extra):
        steps.append({'id': name, 'phase': phase, 'argv': argv, 'timeout_s': timeout, **extra})
    add('preflight', 'preflight', value['preflight_argv'])
    add('numeric-gate', 'numeric', value['numeric_gate_argv'])
    for i, case in enumerate(value['cases']):
        add(f'case-{i:03d}', 'render', [sys.executable, str(Path(__file__).resolve()), 'case', '--config', path,
                                     '--config-sha256', config_hash, '--case-id', case['id']], case['timeout_s'], case_id=case['id'])
    add('verify', 'verify', value['verify_argv'])
    add('review-index', 'review', [sys.executable, str(Path(__file__).resolve()), 'index', '--config', path,
                                 '--config-sha256', config_hash])
    add('actual-review-gate', 'review', value['review_check_argv'])
    add('storage', 'storage', value['storage_argv'])
    atomic_json(destination, {'schema_version': 1, 'steps': steps})
    load_plan(destination)
    print(json.dumps({'plan': str(Path(destination).resolve()), 'steps': len(steps), 'cases': len(value['cases'])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('build', 'case', 'index'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--case-id')
    parser.add_argument('--config-sha256')
    args = parser.parse_args()
    if args.operation == 'build':
        if not args.plan:
            parser.error('--plan required')
        build(args.config, args.plan)
        return 0
    value = config(args.config)
    if args.config_sha256 and digest(args.config) != args.config_sha256:
        raise ValueError('Pipeline configuration changed; rebuild its plan before resuming')
    if args.operation == 'case':
        return run_case(value, args.case_id)
    review_index(value)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
