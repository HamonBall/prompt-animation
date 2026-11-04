"""Exact unreachable-branch compatibility for the profile-7 planted-leg fix.

Never changes recorded producer identities. Pulse/pelvis consumers must execute
again; only pinned free-leg payloads can use this compatibility proof.
"""
import json,hashlib
from pathlib import Path
from tools.artifact_store import digest,input_identity
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stages/05.4'
BLOCK="""        if p.version==7 and any(id in requested for id in ('pelvis.position','pelvis.orientation')):
            pelvis=h.rig.pose.bones[self.joints['pelvis'].source_bones[0]]
            pelvis.matrix_basis=self.arm_entry_basis[pelvis.name]
            for side in ('left','right'):
                for part in ('UpLeg','Leg','Foot'):
                    bone=h.bones[side.title()+part]
                    bone.matrix_basis=self.arm_entry_basis[bone.name]
            bpy.context.view_layer.update()
"""


def branch_only(previous,current):
    return current.count(BLOCK)==1 and current.replace(BLOCK,'',1)==previous


def execution_identity(manifest):
    fields=('bundle_root','asset','motion','state','profile','measurements','expected_frames','frame_start','frame_end','fps','fps_base','entry','verification')
    return hashlib.sha256(json.dumps({k:manifest.get(k) for k in fields},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def compatible(plan,record,manifest,result,executable,*,current_producer,previous_source,current_source):
    if plan.get('owner')!='05.4-planted-rebase' or plan.get('status')!='verified_unreachable_branch' or plan.get('schema_version')!=1:return False
    if current_producer!=plan.get('current_producer_sha256') or not branch_only(previous_source,current_source):return False
    if manifest['inputs']!=record['inputs'] or result['stage_05_4']['application_producer_sha256']!=plan.get('previous_producer_sha256'):return False
    if executable['entry_snapshot']['profile_version']!=7 or result['stage_05_4']['case'].startswith('knee.pulse.'):return False
    if not executable['tracks'] or any(t['control_id'] in ('pelvis.position','pelvis.orientation') for t in executable['tracks']):return False
    return execution_identity(manifest)==record['execution_identity']


def inputs_valid(directory,manifest,result):
    directory=Path(directory);current=input_identity(directory)
    if manifest['inputs']==current:return True
    try:
        plan=json.loads((OUT/'planted-rebase-migration.json').read_text());key=directory.relative_to(OUT).as_posix();record=plan['cases'][key]
        if {k:v for k,v in current.items() if k!='producer_sha256'}!={k:v for k,v in manifest['inputs'].items() if k!='producer_sha256'}:return False
        if manifest['inputs']['producer_sha256']!=plan['previous_producer_sha256']:return False
        previous=OUT/'primitive-before-planted-rebase.py';source=ROOT/'src/avatar_app/blender/primitive.py'
        if digest(previous)!=plan['previous_primitive_sha256'] or digest(source)!=plan['current_primitive_sha256']:return False
        if not compatible(plan,record,manifest,result,json.loads((directory/'executable.json').read_text()),
                current_producer=current['producer_sha256'],previous_source=previous.read_text(),current_source=source.read_text()):return False
        for name in ('result.json','motion.blend','native-process.json'):
            p=directory/name;item=record['payloads'][name];stat=p.stat()
            if digest(p)!=item['sha256'] or stat.st_size!=item['bytes'] or stat.st_mtime_ns!=item['mtime_ns']:return False
        return True
    except (OSError,KeyError,ValueError,TypeError):return False
