"""Additional full-motion hand closeups, using the shared renderer/media writer."""
from pathlib import Path
import argparse,json,shutil,sys
import bpy
from mathutils import Vector,Quaternion
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.limbs import shoulder_position
from avatar_app.blender import rig_profile as rp
from tools.hands_evidence_cases import cases,detail_cases
from tools.artifact_store import producer_lease,open_preview,write_manifest,atomic_json,digest
from tools.hands_render_state import render_complete
from tools.artifact_bundle import validate_manifest
from tools.movement_evidence import render
from tools.lossless_evidence import recover_evidence,encode_view,retire_pngs
from tools.storage_policy import enforce
OUT=ROOT/'artifacts/stages/05.3a'


parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True,choices=('demo','mixamo'))
parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=1);parser.add_argument('--pilot',action='store_true')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert 0<=args.shard<args.shards<=8
selected=[row for i,row in enumerate(detail_cases()) if i%args.shards==args.shard]
if args.pilot:selected=[row for row in selected if row[0]=='elbow.flex.default']
p=c.loads(c.AvatarProfile,(OUT/args.rig/'profile.json').read_text())
for name,id,_,_ in selected:
    out=OUT/args.rig/name
    assert render_complete(out,('front','side'))
    existing=json.loads((out/'preview-manifest.json').read_text())
    if render_complete(out,('front','side','hand-front','hand-side')) and all(
        existing['views'][v].get('renderer_sha256')==digest(Path(__file__)) for v in ('hand-front','hand-side')):
        print('HANDS_DETAIL_REUSED',args.rig,name,flush=True);continue
    with producer_lease(out):
        recover_evidence(out);manifest,asset,motion=validate_manifest(out);before=(digest(motion),motion.stat().st_mtime_ns)
        result=json.loads((out/'result.json').read_text());entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text())
        instance=c.loads(c.MovementInstance,(out/'instance.json').read_text());parameters={x.name:x.value for x in instance.parameters}
        sides=('left','right') if parameters['side']=='both' else (parameters['side'],);values={x.control_id:x.value for x in entry.measured_controls}
        basis=Quaternion(entry.root_transform.orientation).to_matrix();h=open_preview(out);owned=[];materials=[]
        for side in sides:
            for suffix,color in (('palm-normal',(1,.8,.02,1)),('finger-forward',(.02,.8,1,1))):
                curve=bpy.data.curves.new('Measured '+suffix,'CURVE');curve.dimensions='3D';curve.bevel_depth=.0018;curve.bevel_resolution=2
                spline=curve.splines.new('POLY');spline.points.add(1)
                obj=bpy.data.objects.new('Measured '+side+' '+suffix,curve);h.scene.collection.objects.link(obj)
                obj.show_in_front=True
                material=bpy.data.materials.new('Evidence '+side+' '+suffix);material.diffuse_color=color;curve.materials.append(material)
                owned.append((obj,side,suffix));materials.append(material)
        views=dict(manifest['views']);plans=[];scratch=out/'.scratch'/'hand-detail';scratch.mkdir(parents=True,exist_ok=True)
        assert scratch.resolve().is_relative_to(out.resolve())
        shutil.copy2(out/'result.json',scratch/'result.json')
        try:
            for side_view in (False,True):
                view='hand-side' if side_view else 'hand-front'
                observed_side=sides[int(side_view)] if len(sides)==2 else sides[0]
                points=[Vector(sample['measured'][observed_side+'.hand.position']) for sample in result['samples']]
                center=sum(points,Vector())/len(points)
                # Include the actual 10 cm reference rays without fitting the
                # shoulder, which can make subtle palm changes unreadably small.
                scale=max((v-center).length for v in points)*2.3+.36
                def observe(scene,*unused):
                    if scene!=h.scene:return
                    camera=scene.camera;camera.data.ortho_scale=scale
                    camera.location=center+(basis.col[0] if side_view else basis.col[1])*4
                    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
                    for obj,side,suffix in owned:
                        point=Vector(rp.measure_endpoint(h,p,side+'.hand'));q=Quaternion(rp.measure_orientation(h,p,side+'.hand'))
                        direction=q @ Vector((0,0,1) if suffix=='palm-normal' else (0,1,0))
                        obj.data.splines[0].points[0].co=(*point,1)
                        obj.data.splines[0].points[1].co=(*(point+direction*.10),1)
                bpy.app.handlers.frame_change_post.append(observe)
                try:views[view]=render(h,p,scratch,side_view)
                finally:bpy.app.handlers.frame_change_post.remove(observe)
                label='side' if side_view else 'front';destination=out/view
                if destination.exists():
                    assert not any(destination.iterdir()),'Recover owned detail PNGs before replacing a nonempty directory'
                    destination.rmdir()
                (scratch/label).rename(destination);(scratch/(label+'-sheet.png')).replace(out/(view+'-sheet.png'))
                media,plan=encode_view(out,view,manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base'])
                views[view].update(media=media,renderer_sha256=digest(Path(__file__)),observed_side=observed_side,
                    framing='active hand trajectory plus measured axes; bilateral front=left and side=right',
                    observed_axes={'yellow':'actual palm normal','cyan':'actual finger-forward'})
                plans.append(plan)
        finally:
            for obj,_,_ in owned:
                curve=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.curves.remove(curve)
            for material in materials:bpy.data.materials.remove(material)
            (scratch/'result.json').unlink(missing_ok=True)
            if not any(scratch.iterdir()):scratch.rmdir()
        h.scene.frame_set(1);write_manifest(out,h.scene,views=views,complete=True);retire_pngs(out,plans)
        assert before==(digest(motion),motion.stat().st_mtime_ns)
        enforce(out);print('HANDS_DETAIL_PASSED',args.rig,name,flush=True)
print('ALL_HANDS_DETAIL_SHARD_PASSED',args.rig,args.shard,flush=True)
