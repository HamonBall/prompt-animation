"""Strict harness-only compatibility for an unexecuted authored-sequence branch.

All application-source identity checks remain exact. This never changes recorded
producer identities or permits reuse after an application/solver change.
"""
import json
from pathlib import Path
from tools import artifact_store as store
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stages/05.3b'
HARNESS='tests/blender_movement_fingers.py'
OLD_LINE='for key in (t.control_id for t in fragment.tracks):'
NEW_LINE="for key in (t.control_id for t in fragment.tracks if t.control_id.endswith('.curl')):"


def sequence_only_change(previous,current):
    return previous.count(OLD_LINE)==1 and previous.replace(OLD_LINE,NEW_LINE,1)==current


def compatible_record(plan,*,key,fixture,previous,current,inputs,result_sha,motion_sha,mtime_ns):
    if plan.get('owner')!='stage-05.3b-sequence-fixture' or plan.get('schema_version')!=1 or plan.get('status')!='verified_unexecuted_branch_change':return False
    if fixture=='sequence' or previous!=plan.get('previous_harness_sha256') or current!=plan.get('current_harness_sha256'):return False
    record=plan.get('cases',{}).get(key)
    return bool(record and record['inputs']==inputs and record['result_sha256']==result_sha
                and record['motion_sha256']==motion_sha and record['motion_mtime_ns']==mtime_ns)


def producer_valid(directory):
    directory=Path(directory)
    try:
        result=json.loads((directory/'result.json').read_text());producer=result['stage_05_3b']['stage_producer']
        changed={str(Path(key)).replace('\\','/'):value for key,value in producer.items() if store.digest(ROOT/key)!=value}
        if not changed:return True
        if set(changed)!={HARNESS} or result['stage_05_3b']['fixture']=='sequence':return False
        plan=json.loads((OUT/'sequence-harness-migration.json').read_text());current=ROOT/HARNESS;previous=OUT/plan['previous_source_path']
        if changed[HARNESS]!=plan['previous_harness_sha256'] or store.digest(previous)!=plan['previous_harness_sha256'] or store.digest(current)!=plan['current_harness_sha256']:return False
        if not sequence_only_change(previous.read_text(),current.read_text()):return False
        key=directory.resolve().relative_to(OUT.resolve()).as_posix()
        motion=directory/'motion.blend';manifest=json.loads((directory/'preview-manifest.json').read_text())
        return (manifest['inputs']==store.input_identity(directory) and compatible_record(plan,key=key,
            fixture=result['stage_05_3b']['fixture'],previous=changed[HARNESS],current=store.digest(current),
            inputs=manifest['inputs'],result_sha=store.digest(directory/'result.json'),motion_sha=store.digest(motion),mtime_ns=motion.stat().st_mtime_ns))
    except (OSError,KeyError,ValueError,TypeError):return False
