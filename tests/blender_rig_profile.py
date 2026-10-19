"""Stage 03 real-rig calibration/measurement checks, no movement executor.

blender -b --factory-startup --python-exit-code 1 --python tests/blender_rig_profile.py -- --render
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from avatar_app.blender.avatar import import_avatar, discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.kinematics import aim
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.movement_library import contracts as c

OUT = ROOT/'artifacts/stages/03'
FIXTURES = ROOT/'tests/fixtures/rig_profiles'
OUT.mkdir(parents=True,exist_ok=True)
FIXTURES.mkdir(parents=True,exist_ok=True)
REVISION = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()+':stage03-working-tree'
REPORT = {'calibration_version':1,'angle_tolerance_deg':rp.ANGLE_TOLERANCE_DEG,
          'position_tolerance_m':rp.POSITION_TOLERANCE_M,'rigs':{}}


def reset(handle):
    for bone in handle.rig.pose.bones: bone.matrix_basis.identity()
    bpy.context.view_layer.update()


def rotate_world(handle,bone,axis,angle):
    world = handle.rig.matrix_world @ bone.matrix
    origin = world.translation.copy()
    q = Quaternion(axis,math.radians(angle))
    result = Matrix.Translation(origin) @ q.to_matrix().to_4x4() @ Matrix.Translation(-origin) @ world
    bone.matrix = handle.rig.matrix_world.inverted() @ result
    bpy.context.view_layer.update()


def scalar_target(handle,profile,control_id,target):
    control = next(v for v in profile.controls if v.id==control_id)
    limit = next(v for v in profile.joint_limits if v.control_id==control_id)
    mapping = next(v for v in profile.rest_to_semantic_mappings if v.semantic_id==control.chain)
    bone = handle.rig.pose.bones[mapping.source_bones[0]]
    parent = rp.semantic_frame(handle,profile,mapping.parent_id)
    actual = rp.measure_joint_angle(handle,profile,control_id)
    rotate_world(handle,bone,parent.to_3x3() @ Vector(limit.positive_axis),target-actual)


def context_pose(handle,profile,control,context):
    reset(handle)
    if context!='neutral':
        rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],90)
    if context=='turned_bent':
        joint = next(j for j in profile.rest_to_semantic_mappings if j.semantic_id==control.chain)
        parent = next(j for j in profile.rest_to_semantic_mappings if j.semantic_id==joint.parent_id)
        bone = handle.rig.pose.bones[parent.source_bones[0]]
        axis = rp.semantic_frame(handle,profile,parent.semantic_id).to_3x3().col[0]
        rotate_world(handle,bone,axis,37)
    if context in ('wrist_horizontal','wrist_overhead'):
        side = control.id.split('.')[0].title()
        frame = rp.semantic_frame(handle,profile,'pelvis').to_3x3()
        direction = frame.col[2] if context=='wrist_overhead' else frame.col[0]*(-1 if side=='Left' else 1)
        local = handle.rig.matrix_world.inverted().to_3x3() @ direction
        aim(handle.bones[side+'Arm'],local)
        aim(handle.bones[side+'ForeArm'],local)


def signature(handle):
    """Geometry/material/rest data, plus current pose and normalization hierarchy."""
    payload = []
    for bone in handle.rig.data.bones:
        payload.append((bone.name,tuple(x for row in bone.matrix_local for x in row)))
    for obj in handle.objects:
        payload.append((obj.name,tuple(x for row in obj.matrix_world for x in row)))
        if obj.type=='MESH':
            payload.append((obj.name,len(obj.data.polygons),tuple(tuple(v.co) for v in obj.data.vertices),
                            tuple(slot.material.name if slot.material else None for slot in obj.material_slots)))
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def marker(handle,start,vector,color,name):
    data = bpy.data.curves.new(name,'CURVE'); data.dimensions='3D'; data.bevel_depth=.004
    spline = data.splines.new('POLY'); spline.points.add(1)
    spline.points[0].co=(*start,1); spline.points[1].co=(*(start+vector),1)
    obj=bpy.data.objects.new(name,data); handle.scene.collection.objects.link(obj)
    material=bpy.data.materials.new(name); material.diffuse_color=(*color,1)
    obj.data.materials.append(material); handle.environment.append(obj)
    return obj


def render_axes(handle,profile,path,palm=False):
    if handle.scene.camera is None: prepare_preview(handle)
    made=[]
    for joint in ('pelvis','head','left.wrist','right.wrist','left.shin','right.shin'):
        frame=rp.semantic_frame(handle,profile,joint)
        start=frame.translation+rp._character_basis(handle).col[1]*.13
        for index,color in enumerate(((1,.08,.05),(.05,.9,.12),(.1,.35,1))):
            made.append(marker(handle,start,frame.to_3x3().col[index]*.13,color,joint+'.XYZ'[index+1]))
    if palm:
        for side in ('left','right'):
            q=Quaternion(rp.measure_orientation(handle,profile,side+'.hand'))
            start=Vector(rp.measure_endpoint(handle,profile,side+'.hand'))
            made.append(marker(handle,start,q @ Vector((0,0,.22)),(1,.75,.03),side+'.palm_normal'))
    for endpoint in ('left.hand','right.hand','left.sole','right.sole'):
        point=Vector(rp.measure_endpoint(handle,profile,endpoint))
        draw=point+rp._character_basis(handle).col[1]*.18+rp._character_basis(handle).col[2]*.03
        made.append(marker(handle,point,draw-point,(1,.1,.8),endpoint+'.leader'))
        for direction in (Vector((.018,0,0)),Vector((0,.018,0)),Vector((0,0,.018))):
            made.append(marker(handle,draw-direction,direction*2,(1,.1,.8),endpoint+'.landmark'))
    scene=handle.scene
    scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.light='STUDIO'; scene.display.shading.color_type='MATERIAL'
    scene.display.shading.show_shadows=True; scene.display.shading.show_cavity=True
    scene.render.resolution_x=850; scene.render.resolution_y=850; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'; scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    for obj in made:
        data=obj.data; materials=list(data.materials)
        handle.environment.remove(obj); bpy.data.objects.remove(obj,do_unlink=True)
        if data.users==0: bpy.data.curves.remove(data)
        for material in materials:
            if material.users==0: bpy.data.materials.remove(material)


def run_rig(name,handle):
    started=time.perf_counter()
    before=signature(handle)
    bases={b.name:b.matrix_basis.copy() for b in handle.rig.pose.bones}
    profile=rp.calibrate_joint_frames(handle,avatar_id=name,source_revision=REVISION,recorded_at='2026-10-19')
    assert signature(handle)==before
    assert all(b.matrix_basis==bases[b.name] for b in handle.rig.pose.bones)
    assert c.loads(c.AvatarProfile,c.dumps(profile))==profile
    assert rp.calibrate_joint_frames(handle,avatar_id=name,source_revision=REVISION,recorded_at='2026-10-19')==profile
    inspection=rp.inspect_capabilities(handle)
    rows=[]
    for control in profile.controls:
        if control.value_shape!='scalar': continue
        limit=next(l for l in profile.joint_limits if l.control_id==control.id)
        contexts=['neutral','turned','turned_bent']
        if '.wrist.' in control.id: contexts+=['wrist_horizontal','wrist_overhead']
        for context in contexts:
            for expected in sorted(set((limit.minimum,-5,0,20,limit.maximum))):
                context_pose(handle,profile,control,context)
                scalar_target(handle,profile,control.id,expected)
                measured=rp.measure_joint_angle(handle,profile,control.id)
                error=abs((measured-expected+180)%360-180)
                rows.append({'control':control.id,'context':context,'applied_deg':expected,'measured_deg':measured,'error_deg':error})
                assert error <= rp.ANGLE_TOLERANCE_DEG,(name,rows[-1])
    # Signed mirror quantities and world reflection of paired endpoint positions.
    mirrors=[]
    for left in (v for v in profile.controls if v.id.startswith('left.') and v.value_shape=='scalar'):
        limit=next(l for l in profile.joint_limits if l.control_id==left.id)
        if limit.mirror_control_id is None: continue
        for context in ('neutral','turned','turned_bent'):
            context_pose(handle,profile,left,context)
            scalar_target(handle,profile,left.id,20)
            scalar_target(handle,profile,limit.mirror_control_id,20*limit.mirror_sign)
            a=rp.measure_joint_angle(handle,profile,left.id)
            b=rp.measure_joint_angle(handle,profile,limit.mirror_control_id)
            assert abs(a-limit.mirror_sign*b)<rp.ANGLE_TOLERANCE_DEG
            mirrors.append({'left':left.id,'context':context,'left_deg':a,'right_deg':b})
    # Explicit physical sign checks independent of calibration's requested numbers.
    signs=[]
    for context in ('neutral','turned'):
        for side in ('left','right'):
            reset(handle)
            if context=='turned': rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],90)
            frame=rp.semantic_frame(handle,profile,'pelvis').to_3x3()
            key=side.title()
            before_hand=Vector(rp.measure_endpoint(handle,profile,side+'.hand'))
            scalar_target(handle,profile,side+'.elbow.flexion',40)
            after_hand=Vector(rp.measure_endpoint(handle,profile,side+'.hand'))
            assert (after_hand-before_hand).dot(frame.col[1])>0,(name,'elbow sign')
            reset(handle)
            if context=='turned': rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],90)
            scalar_target(handle,profile,side+'.hip.flexion',50)
            before_foot=Vector(rp.measure_endpoint(handle,profile,side+'.foot'))
            scalar_target(handle,profile,side+'.knee.flexion',60)
            after_foot=Vector(rp.measure_endpoint(handle,profile,side+'.foot'))
            assert (after_foot-before_foot).dot(frame.col[1])<0,(name,'knee sign')
            signs.append({'side':side,'context':context,'elbow_forward':True,'knee_back_after_hip_raised':True})
            for quantity,reference in (('flexion','normal'),('deviation','radial')):
                control=next(v for v in profile.controls if v.id==side+'.wrist.'+quantity)
                for wrist_context in ('wrist_horizontal','wrist_overhead'):
                    context_pose(handle,profile,control,wrist_context)
                    hand=handle.bones[side.title()+'Hand']
                    before_direction=(handle.rig.matrix_world.to_3x3() @ (hand.tail-hand.head)).normalized()
                    landmark=next(v for v in profile.landmarks if v.id==side+'.palm.'+reference)
                    direction=rp.semantic_frame(handle,profile,side+'.wrist').to_3x3() @ Vector(landmark.position)
                    scalar_target(handle,profile,control.id,15)
                    after_direction=(handle.rig.matrix_world.to_3x3() @ (hand.tail-hand.head)).normalized()
                    assert (after_direction-before_direction).dot(direction)>0,(name,side,quantity,wrist_context)
    poles=[]
    for side in ('left','right'):
        for limb,control in (('forearm','elbow.flexion'),('shin','knee.flexion')):
            for yaw in (0,90):
                reset(handle)
                rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],yaw)
                vectors=[]
                for target in (-.001,0,.001,.49,.51):
                    scalar_target(handle,profile,side+'.'+control,target)
                    vectors.append(Vector(rp.measure_bend_plane(handle,profile,side+'.'+limb)))
                dots=[vectors[i].dot(vectors[i+1]) for i in range(len(vectors)-1)]
                assert min(dots)>.99,(name,side,limb,dots)
                poles.append({'limb':side+'.'+limb,'yaw':yaw,'min_adjacent_dot':min(dots)})
    # The two rigs have different bind hands; palm-up is an actual normal, not hand_roll.
    palm_up=[]
    for yaw in (0,90):
        reset(handle)
        rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],yaw)
        for side in ('left','right'):
            key=side.title(); root_frame=rp.semantic_frame(handle,profile,'pelvis').to_3x3()
            outward=root_frame.col[0]*(-1 if side=='left' else 1)
            local=handle.rig.matrix_world.inverted().to_3x3() @ outward
            aim(handle.bones[key+'Arm'],local); aim(handle.bones[key+'ForeArm'],local)
            axis=root_frame.col[0]
            normal=Quaternion(rp.measure_orientation(handle,profile,side+'.hand')) @ Vector((0,0,1))
            target=rp._project(root_frame.col[2],axis)
            initial=rp._project(normal,axis)
            angle=math.degrees(math.atan2(axis.dot(initial.cross(target)),initial.dot(target)))
            rotate_world(handle,handle.bones[key+'ForeArm'],axis,angle)
            achieved=Quaternion(rp.measure_orientation(handle,profile,side+'.hand')) @ Vector((0,0,1))
            # Imported bind wrists are not exactly collinear with the forearm.
            # Set a static wrist fixture to remove that residual; this is not a
            # movement builder or a claim that forearm twist also bends the wrist.
            wrist_correction=achieved.rotation_difference(root_frame.col[2])
            correction_axis,correction_angle=wrist_correction.to_axis_angle()
            rotate_world(handle,handle.bones[key+'Hand'],correction_axis,math.degrees(correction_angle))
            achieved=Quaternion(rp.measure_orientation(handle,profile,side+'.hand')) @ Vector((0,0,1))
            dot=achieved.dot(root_frame.col[2])
            residual=math.degrees(achieved.angle(root_frame.col[2]))
            assert residual<=3,(name,side,'palm-up',residual)
            palm_up.append({'side':side,'root_yaw':yaw,'normal_up_dot':dot,
                            'palm_up_residual_deg':residual,'static_bind_wrist_correction_deg':math.degrees(correction_angle)})
        if yaw==90 and '--render' in sys.argv: render_axes(handle,profile,OUT/(name+'-turned-palm-up.png'),True)
    reset(handle)
    neutral=rp.capture_motion_state(handle,profile,revision=17)
    assert neutral.velocities is None and neutral.phase is None and neutral.revision==17
    anchors=tuple(c.ContactAnchor(side+'.sole','floor',rp.measure_endpoint(handle,profile,side+'.sole'),'world','metre')
                  for side in ('left','right'))
    contact=rp.capture_motion_state(handle,profile,revision=18,contact_anchors=anchors,
                                     active_contacts=tuple(a.anchor_id for a in anchors))
    assert contact.active_contacts==('left.sole','right.sole')
    pose_before={b.name:b.matrix_basis.copy() for b in handle.rig.pose.bones}
    rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],90)
    current=rp.capture_motion_state(handle,profile,revision=19)
    assert Quaternion(current.root_transform.orientation).rotation_difference(Quaternion(neutral.root_transform.orientation)).angle>1.5
    turned_before={b.name:b.matrix_basis.copy() for b in handle.rig.pose.bones}
    posed_calibration=rp.calibrate_joint_frames(handle,avatar_id=name,source_revision=REVISION,recorded_at='2026-10-19')
    assert posed_calibration==profile
    assert all(b.matrix_basis==turned_before[b.name] for b in handle.rig.pose.bones)
    # Independently predicted rigid transform of the measured endpoints/sole/palm.
    reset(handle)
    endpoints={e:Vector(rp.measure_endpoint(handle,profile,e))
               for e in ('left.hand','right.hand','left.foot','right.foot','left.sole','right.sole')}
    orientations={e:Quaternion(rp.measure_orientation(handle,profile,e))
                  for e in ('left.hand','right.hand','left.foot','right.foot')}
    origin=handle.rig.matrix_world @ handle.bones['Hips'].head
    q=Quaternion(rp._character_basis(handle).col[2],math.pi/2)
    displacement=Vector((.13,-.09,.07))
    rotate_world(handle,handle.bones['Hips'],rp._character_basis(handle).col[2],90)
    world=handle.rig.matrix_world @ handle.bones['Hips'].matrix
    world.translation+=displacement
    handle.bones['Hips'].matrix=handle.rig.matrix_world.inverted() @ world
    bpy.context.view_layer.update()
    position_errors={e:(Vector(rp.measure_endpoint(handle,profile,e))-(origin+q @ (p-origin)+displacement)).length
                     for e,p in endpoints.items()}
    orientation_errors={e:abs((math.degrees((q @ before).rotation_difference(Quaternion(rp.measure_orientation(handle,profile,e))).angle)+180)%360-180)
                        for e,before in orientations.items()}
    assert max(position_errors.values())<=rp.POSITION_TOLERANCE_M,(name,position_errors)
    assert max(orientation_errors.values())<=rp.ANGLE_TOLERANCE_DEG,(name,orientation_errors)
    reset(handle)
    scale=handle.rig.scale.copy()
    handle.rig.scale=scale*1.1
    bpy.context.view_layer.update()
    try:
        rp.capture_motion_state(handle,profile,revision=20)
        raise AssertionError('Stale scale calibration accepted')
    except c.MotionContractError as error: assert error.code=='ENTRY_MISMATCH'
    finally:
        handle.rig.scale=scale
        bpy.context.view_layer.update()
    bind_wrist_angles={side:math.degrees(rp._rest_direction(handle,handle.bones[side.title()+'ForeArm']).angle(
        rp._rest_direction(handle,handle.bones[side.title()+'Hand']))) for side in ('left','right')}
    if name=='mixamo': assert abs(bind_wrist_angles['left']-bind_wrist_angles['right'])>.001
    reset(handle)
    if '--render' in sys.argv: render_axes(handle,profile,OUT/(name+'-axes.png'))
    # Preview annotations may add objects; original avatar mesh/rest/material/scale remain exact.
    avatar_objects=[o for o in handle.objects if o.type in ('MESH','ARMATURE','EMPTY')]
    original_objects=handle.objects
    handle.objects=avatar_objects
    assert signature(handle)==before,(name,'asset preservation')
    handle.objects=original_objects
    snapshot_json=OUT/(name+'-snapshot.json')
    snapshot_json.write_text(c.dumps(neutral)+'\n',encoding='utf-8')
    (FIXTURES/(name+'.json')).write_text(json.dumps(c.to_dict(profile),sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return {'height_m':profile.height_m,'control_count':len(profile.controls),'axis_cases':rows,'mirror_cases':mirrors,
            'physical_signs':signs,'pole_continuity':poles,'palm_up':palm_up,
            'max_angle_error_deg':max(row['error_deg'] for row in rows),
            'position_errors_m':position_errors,'orientation_errors_deg':orientation_errors,
            'asymmetric_bind_wrist_angles_deg':bind_wrist_angles,'scale_change_requires_recalibration':True,
            'segment_ratios':{v.id:v.value_m/profile.height_m for v in profile.lengths if v.id in ('left.upper_arm','left.thigh')},
            'missing_optional':list(inspection.missing_optional),'available_optional':list(inspection.available),
            'rest_mesh_material_scale_preserved':True,'calibration_preserves_current_pose':True,
            'elapsed_seconds':time.perf_counter()-started}


for name in ('demo','mixamo'):
    handle=create_demo_avatar() if name=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
    REPORT['rigs'][name]=run_rig(name,handle)
    print('RIG_PROFILE_VERIFIED',name,REPORT['rigs'][name]['max_angle_error_deg'],flush=True)
    discard_avatar(handle)

handle=import_avatar(str(ROOT/'Hip Hop Andrejs.fbx'))
profile=rp.calibrate_joint_frames(handle,avatar_id='andrejs-negative',source_revision=REVISION,recorded_at='2026-10-19')
inspection=rp.inspect_capabilities(handle)
assert 'reference.left.palm' in inspection.missing_optional
assert 'left.wrist.flexion' not in {v.id for v in profile.controls}
try:
    rp.measure_orientation(handle,profile,'left.hand')
    raise AssertionError('Missing palm was fabricated')
except c.MotionContractError as error: assert error.code=='MISSING_CAPABILITY'
try:
    demo=c.loads(c.AvatarProfile,(FIXTURES/'demo.json').read_text(encoding='utf-8'))
    rp.capture_motion_state(handle,demo,revision=0)
    raise AssertionError('Different rig profile accepted')
except c.MotionContractError as error: assert error.code=='ENTRY_MISMATCH'
REPORT['andrejs_negative']={'missing_optional':inspection.missing_optional,'palm_measurement_rejected':True,'wrong_rig_rejected':True}
discard_avatar(handle)
assert REPORT['rigs']['demo']['segment_ratios']!=REPORT['rigs']['mixamo']['segment_ratios']
(OUT/'profile-review.json').write_text(json.dumps(REPORT,sort_keys=True,indent=2)+'\n',encoding='utf-8')
manifest={'schema_version':1,'calibration_version':1,'profiles':['demo.json','mixamo.json'],
          'angle_tolerance_deg':rp.ANGLE_TOLERANCE_DEG,'position_tolerance_m':rp.POSITION_TOLERANCE_M,
          'evidence':'artifacts/stages/03/profile-review.json','source_revision':REVISION}
(FIXTURES/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
print('ALL_RIG_PROFILE_CHECKS_PASSED',flush=True)
