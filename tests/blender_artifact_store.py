"""Real v2 repeat/failure writes and verified cleanup of owned v1 save copies."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools import artifact_store as store
from tools.artifact_bundle import trajectory,capture_state
from tools.blender_artifact_worker import signature,equivalence,verify_saved_measurements
from tools.storage_v2 import OUT,append_event

report={};scratch=OUT/'.scratch';scratch.mkdir(exist_ok=True)
for rig in ('demo','mixamo'):
    case=ROOT/'artifacts/maintenance/neutral-artifacts/new-spine'/rig/'torso.wave.default'
    with tempfile.TemporaryDirectory(dir=scratch,prefix='save-repeat-') as temporary:
        folder=Path(temporary).resolve();assert folder.is_relative_to(scratch.resolve())
        store.open_preview(case);before=signature();numeric=verify_saved_measurements(case)
        bpy.context.scene.frame_set(before['current_frame']);trajectory(folder/'trajectory.f32.gz')
        old=ROOT/'artifacts/maintenance/neutral-artifacts/save-tests'/rig/'preview.blend'
        if old.exists():
            old_hash=store.digest(old);old_bytes=old.stat().st_size
            bpy.ops.wm.open_mainfile(filepath=str(old),load_ui=False,use_scripts=False)
            equivalence(before,signature());trajectory(folder/'trajectory.f32.gz',expected=True)
            append_event({'operation':'owned_save_copy_verified','path':str(old),'sha256':old_hash,'bytes':old_bytes,'accepted_case':str(case)})
            if store.digest(old)!=old_hash:raise RuntimeError('Owned copy changed before retirement')
            old.unlink();append_event({'operation':'owned_save_copy_retired','path':str(old),'sha256':old_hash,'bytes':old_bytes})
        store.open_preview(case)
        output=folder/'routine';output.mkdir()
        preferences=bpy.context.preferences.filepaths;original=preferences.save_version
        try:
            preferences.save_version=7
            for _ in range(2):
                store.save_scene(output/'preview.blend');assert preferences.save_version==7
            manifest=store.digest(output/'preview-manifest.json');motion=store.digest(output/'motion.blend')
            names=sorted(p.name for p in output.iterdir())
            with patch.object(store.os,'replace',side_effect=OSError('injected atomic replacement failure')):
                try:store.save_scene(output/'preview.blend');raise AssertionError('Injection did not fail')
                except OSError:pass
            assert store.digest(output/'motion.blend')==motion and store.digest(output/'preview-manifest.json')==manifest
            assert preferences.save_version==7
            assert not list(output.rglob('*.blend1')) and not (output/'preview.blend').exists()
            # Reconcile the deliberate failed candidate before the next write.
            (output/'motion.pending.blend').unlink(missing_ok=True);(output/'preview-manifest.pending.json').unlink(missing_ok=True)
            assert sorted(p.name for p in output.iterdir())==names
            store.open_preview(output);equivalence(before,signature());trajectory(folder/'trajectory.f32.gz',expected=True)
            report[rig]={'numeric_error':numeric,'full_playback':True,'repeat_no_growth':True,'replacement_failure':True,
                         'no_backups':True,'preferences_restored':True,'motion_bytes':(output/'motion.blend').stat().st_size}
        finally:preferences.save_version=original
    print('BLENDER_ARTIFACT_STORE_PASSED',rig,flush=True)
store.atomic_json(OUT/'save-review.json',report)
print('ALL_BLENDER_ARTIFACT_STORE_CHECKS_PASSED',flush=True)
