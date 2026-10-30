"""Explicit, hash-pinned compatibility for the unchanged non-endpoint code path.

This is not a general stale-source override. An endpoint or pole track always
requires regeneration. Original execution producer identities remain intact.
"""
import json
from pathlib import Path
from tools.artifact_store import input_identity,digest
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stages/05.3a'


def endpoint_controls(ids):
    return any(id.endswith(('.hand.position','.hand.torso_position','.elbow.plane')) for id in ids)


def compatible_record(plan,key,current,execution_producer,ids,inputs,motion_sha,mtime_ns):
    try:
        record=plan['cases'][key]
        return (plan.get('schema_version')==1 and plan.get('owner')=='stage-05.3a-endpoint-baseline-fix' and
                plan['status']=='source_compatibility_verified' and plan['current_producer_sha256']==current and
                execution_producer==plan['previous_producer_sha256'] and not record['affected'] and not endpoint_controls(ids) and
                record['inputs']==inputs and record['motion_sha256']==motion_sha and record['motion_mtime_ns']==mtime_ns)
    except (KeyError,TypeError):return False


def numeric_source_valid(directory,identity=None):
    directory=Path(directory);identity=identity or input_identity(directory)
    try:
        result=json.loads((directory/'result.json').read_text())
        if result.get('producer_sha256')==identity['producer_sha256']:return True
        plan=json.loads((OUT/'endpoint-baseline-migration.json').read_text())
        key=directory.resolve().relative_to(OUT.resolve()).as_posix()
        motion=json.loads((directory/'executable.json').read_text())
        return compatible_record(plan,key,identity['producer_sha256'],result['producer_sha256'],
            (t['control_id'] for t in motion['tracks']),{k:v for k,v in identity.items() if k!='producer_sha256'},
            digest(directory/'motion.blend'),(directory/'motion.blend').stat().st_mtime_ns)
    except (OSError,ValueError,KeyError,TypeError):return False
