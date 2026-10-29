"""Real bundle relocation, custom state, distinct rig and explicit export checks."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import open_preview,digest,atomic_json
from tools.artifact_bundle import capture_state,trajectory,validate_manifest,write_bundle
from tools.blender_artifact_worker import signature
from tools.load_artifact import export_standalone

OUT=ROOT/'artifacts/maintenance/storage-v2'
if '--verify-relocated' in sys.argv:
    folder=Path(sys.argv[sys.argv.index('--verify-relocated')+1]);case=folder/'artifacts/stages/05.1a/pilot/nod-default'
    expected=json.loads((folder/'expected.json').read_text())
    open_preview(case);sig=signature();state,_=capture_state()
    assert state==expected['state']
    assert {k:v for k,v in sig.items() if k!='poses'}==expected['signature']
    samples=trajectory(folder/'trajectory.f32.gz',expected=True)
    atomic_json(folder/'verified.json',{'passed':True,'playback':samples})
    raise SystemExit(0)

report={};ids=[]
scratch=OUT/'.scratch';scratch.mkdir(exist_ok=True)
for rig in ('demo','mixamo'):
    with tempfile.TemporaryDirectory(dir=scratch,prefix='portability-') as temporary:
        folder=Path(temporary).resolve();assert folder.is_relative_to(scratch.resolve())
        original=ROOT/'artifacts/stages/05.1a'/rig/'nod-default'
        m,asset,motion=validate_manifest(original);ids.append(m['asset']['content_hash'])
        open_preview(original);sig=signature();state,_=capture_state();samples=trajectory(folder/'trajectory.f32.gz')
        atomic_json(folder/'expected.json',{'state':state,'signature':{k:v for k,v in sig.items() if k!='poses'}})
        case=folder/'artifacts/stages/05.1a/pilot/nod-default';case.mkdir(parents=True)
        for p in original.glob('*.json'):shutil.copy2(p,case/p.name)
        shutil.copy2(motion,case/'motion.blend')
        # Keep the original relative profile location and asset reference. No FBX.
        shutil.copy2(original/m['profile']['path'],case.parent/'profile.json')
        target=folder/'artifacts/assets'/asset.parent.name;target.mkdir(parents=True)
        shutil.copy2(asset,target/'avatar.blend');shutil.copy2(asset.with_name('asset.json'),target/'asset.json')
        executable=bpy.app.binary_path
        with (folder/'verify.log').open('w') as stream:
            subprocess.run([executable,'--background','--factory-startup','--python-exit-code','1','--python',__file__,'--',
                            '--verify-relocated',str(folder)],check=True,stdout=stream,stderr=subprocess.STDOUT)
        verified=json.loads((folder/'verified.json').read_text());assert verified['passed']
        export=folder/'export.blend';export_standalone(original,export,temporary=True)
        assert export.exists() and not list(folder.rglob('*.blend1'))
        bpy.ops.wm.open_mainfile(filepath=str(export),load_ui=False,use_scripts=False)
        assert not bpy.data.libraries
        trajectory(folder/'trajectory.f32.gz',expected=True)
        # Case-only custom state must survive save/load and not create an asset.
        rig_object=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
        rig_object['storage-test']={'case':'custom','values':[1,2,3]}
        rig_object.pose.bones[0]['custom-bone']=4.25
        custom=folder/'artifacts/custom';custom.mkdir()
        value,_=write_bundle(custom,root=folder/'artifacts',migration=True)
        from tools.artifact_bundle import commit_bundle,open_bundle
        commit_bundle(custom);open_bundle(custom,root=folder/'artifacts')
        observed,_=capture_state();assert observed==value['state']
        assert value['asset']['content_hash']==m['asset']['content_hash']
        malformed=json.loads((custom/'preview-manifest.json').read_text());malformed['state']['bindings'][0]['slot']='missing-slot'
        atomic_json(custom/'preview-manifest.json',malformed)
        try:open_bundle(custom,root=folder/'artifacts');raise AssertionError('Changed slot was accepted')
        except RuntimeError as error:assert 'slot' in str(error)
        report[rig]={'relocated_fresh_process':verified,'standalone_reopen':True,'custom_state':True,'changed_slot_rejected':True,
                     'asset_content_hash':m['asset']['content_hash'],'frames':samples['frames']}
assert len(set(ids))==2,'Different rig versions incorrectly shared'
atomic_json(OUT/'portability-review.json',report)
print('ALL_BUNDLE_PORTABILITY_CHECKS_PASSED',flush=True)
