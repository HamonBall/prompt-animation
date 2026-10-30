"""Restore verified pilot closeups after an older two-view resume replaced metadata."""
import json,sys
from pathlib import Path
from mathutils import Vector,Quaternion
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.limbs import shoulder_position
from tools.artifact_store import producer_lease,open_preview,camera_record,write_manifest,atomic_json,digest
from tools.artifact_bundle import validate_manifest
from tools.lossless_evidence import media_complete,recover_evidence
OUT=ROOT/'artifacts/stages/05.3a';out=OUT/'demo/elbow.flex.default'
with producer_lease(out):
    manifest,asset,motion=validate_manifest(out);before=(digest(motion),motion.stat().st_mtime_ns)
    cache=json.loads((out/'media-build.json').read_text());result=json.loads((out/'result.json').read_text())
    entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());p=c.loads(c.AvatarProfile,(out.parent/'profile.json').read_text())
    values={x.control_id:x.value for x in entry.measured_controls};points=[Vector(s['measured']['left.hand.position']) for s in result['samples']]
    points.append(Vector(shoulder_position(values,p,'left')));center=sum(points,Vector())/len(points)
    scale=max((v-center).length for v in points)*2.3+.12;basis=Quaternion(entry.root_transform.orientation).to_matrix()
    h=open_preview(out);views=dict(manifest['views']);journal={'owner':'stage-05.3a-extra-view-recovery','before_manifest_sha256':digest(out/'preview-manifest.json'),'restored':{}}
    for view,side in (('hand-front',False),('hand-side',True)):
        media=cache['views'][view]['media']
        assert media_complete(out,media,manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base'])
        assert (out/(view+'-sheet.png')).is_file()
        h.scene.camera.data.ortho_scale=scale;h.scene.camera.location=center+(basis.col[0] if side else basis.col[1])*4
        h.scene.camera.rotation_euler=(center-h.scene.camera.location).to_track_quat('-Z','Y').to_euler()
        record=camera_record(h.scene);record.update(media=media,recovered_from_verified_media_build=True,
            camera_construction='Original deterministic hand-detail camera equation and unchanged case inputs',
            observed_axes={'yellow':'actual palm normal','cyan':'actual finger-forward'})
        views[view]=record;journal['restored'][view]={'media_sha256':media['sha256'],'sheet_sha256':digest(out/(view+'-sheet.png'))}
    h.scene.frame_set(1);write_manifest(out,h.scene,views=views,complete=True)
    assert before==(digest(motion),motion.stat().st_mtime_ns)
    journal['after_manifest_sha256']=digest(out/'preview-manifest.json');atomic_json(OUT/'extra-view-recovery.json',journal)
    recover_evidence(out)
print('HANDS_EXTRA_VIEWS_RECOVERED',flush=True)
