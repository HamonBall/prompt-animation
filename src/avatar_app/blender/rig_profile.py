"""Read-only calibration/measurement for the built-in and core Mixamo rigs.

No movement builders or pose application live here. All returned state is v1 plain data.
"""
from dataclasses import dataclass
import hashlib
import json
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from .avatar import map_mixamo_bones
from ..movement_library import contracts as c
from ..movement_library.registry import validate_snapshot

CALIBRATION_VERSION = 1
ANGLE_TOLERANCE_DEG = .1
POSITION_TOLERANCE_M = .0001
POLE_STRAIGHT_THRESHOLD_DEG = .5
POLE_FULL_MEASUREMENT_DEG = 5


@dataclass(frozen=True)
class CapabilityInspection:
    mapped_bones: tuple[tuple[str, str], ...]
    available: tuple[str, ...]
    missing_optional: tuple[str, ...]


def _procedural(handle):
    return handle.rig.get('avatar_reference') == 'procedural-demo-v1'


def inspect_capabilities(handle):
    """Discover named anatomy, not the existence of a movement executor."""
    bones = map_mixamo_bones(handle.rig)
    available, missing = [], []
    groups = {'neck': ('Neck',), 'spine.mid': ('Spine1',), 'spine.upper': ('Spine2',)}
    for side in ('Left', 'Right'):
        key = side.lower()
        groups[key+'.clavicle'] = (side+'Shoulder',)
        groups[key+'.toe'] = (side+'ToeBase',)
        for finger in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
            groups[key+'.finger.'+finger.lower()] = tuple(side+'Hand'+finger+str(i) for i in (1,2,3))
        for segment in ('Arm', 'ForeArm', 'UpLeg', 'Leg'):
            names = tuple(name for name in bones if name.startswith(side+segment+'Twist'))
            groups[key+'.twist.'+segment.lower()] = names or (side+segment+'Twist',)
        palm = all(side+'Hand'+finger+'1' in bones for finger in ('Index','Pinky','Thumb'))
        # The procedural character has an explicit documented palm reference.
        if palm or _procedural(handle): available.append('reference.'+key+'.palm')
        else: missing.append('reference.'+key+'.palm')
    for key, required in groups.items():
        (available if all(name in bones for name in required) else missing).append('anatomy.'+key)
    return CapabilityInspection(tuple(sorted((key,b.name) for key,b in bones.items())),
                                tuple(sorted(available)),tuple(sorted(missing)))


def _bones(handle):
    return map_mixamo_bones(handle.rig)


def _character_basis(handle):
    world = handle.rig.matrix_world.to_3x3()
    up = (world @ handle.up).normalized()
    right = world @ handle.right
    right = (right-up*right.dot(up)).normalized()
    forward = up.cross(right).normalized()
    return Matrix((right,forward,up)).transposed()


def _rest_world(handle, bone):
    return handle.rig.matrix_world @ bone.bone.matrix_local


def _pose_world(handle, bone):
    return handle.rig.matrix_world @ bone.matrix


def _rotation(matrix):
    return matrix.to_quaternion().normalized()


def _tuple(vector):
    return tuple(float(x) for x in vector)


def _fingerprint(handle):
    scale = handle.rig.matrix_world.to_scale()
    data = [(b.name, [round(float(x),6) for row in b.matrix_local for x in row])
            for b in handle.rig.data.bones]
    text = json.dumps([data,[round(float(x),7) for x in scale]],separators=(',',':'))
    return hashlib.sha256(text.encode()).hexdigest()


def _binding(handle, profile):
    if type(profile) is not c.AvatarProfile: c.fail('INVALID_PARAMETER','Expected an AvatarProfile')
    evidence = 'rig_sha256:'+_fingerprint(handle)
    if evidence not in profile.calibration_provenance.evidence:
        c.fail('ENTRY_MISMATCH','Profile belongs to a different skeleton or scale; recalibrate explicitly')
    if profile.version != CALIBRATION_VERSION:
        c.fail('VERSION_MISMATCH','Unsupported rig calibration version; recalibrate explicitly')


def _mappings(bones):
    result = {'pelvis':'Hips', 'torso':'Spine', 'head':'Head'}
    for semantic, source in (('spine.mid','Spine1'),('spine.upper','Spine2'),('neck','Neck')):
        if source in bones: result[semantic] = source
    for side in ('Left','Right'):
        key = side.lower()
        for part, source in (('clavicle','Shoulder'),('upper_arm','Arm'),('forearm','ForeArm'),
                             ('wrist','Hand'),('thigh','UpLeg'),('shin','Leg'),('ankle','Foot'),('toe','ToeBase')):
            if side+source in bones: result[key+'.'+part] = side+source
        for finger in ('Thumb','Index','Middle','Ring','Pinky'):
            for index in range(1,5):
                name = side+'Hand'+finger+str(index)
                if name in bones: result[f'{key}.finger.{finger.lower()}.{index}'] = name
        for segment in ('Arm','ForeArm','UpLeg','Leg'):
            for name in bones:
                if name.startswith(side+segment+'Twist'):
                    suffix = name[len(side+segment+'Twist'):] or '0'
                    result[f'{key}.twist.{segment.lower()}.{suffix}'] = name
    return result


def _rest_direction(handle,bone):
    matrix = handle.rig.matrix_world.to_3x3()
    return (matrix @ (bone.bone.tail_local-bone.bone.head_local)).normalized()


def _project(vector,normal):
    projected = vector-normal*vector.dot(normal)
    if projected.length < 1e-7: c.fail('MISSING_CAPABILITY','Degenerate anatomical reference direction')
    return projected.normalized()


def _palm_reference(handle,bones,side):
    hand = bones[side+'Hand']
    if all(side+'Hand'+finger+'1' in bones for finger in ('Thumb','Index','Pinky')):
        world = handle.rig.matrix_world
        wrist = world @ hand.bone.head_local
        index = world @ bones[side+'HandIndex1'].bone.head_local
        pinky = world @ bones[side+'HandPinky1'].bone.head_local
        longitudinal = ((index+pinky)/2-wrist).normalized()
        radial = _project(index-pinky,longitudinal)
    elif _procedural(handle):
        longitudinal = _rest_direction(handle,hand)
        radial = _project(_character_basis(handle).col[1],longitudinal)
    else:
        return None
    sign = -1 if side == 'Left' else 1
    normal = -sign*longitudinal.cross(radial).normalized()
    return longitudinal,radial,normal


def _rest_skin(handle):
    for obj in handle.objects:
        if obj.type == 'MESH':
            for vertex in obj.data.vertices:
                yield obj,vertex,obj.matrix_world @ vertex.co


def _sole_anchor(handle,bone,up):
    points = []
    for obj,vertex,point in _rest_skin(handle):
        group = obj.vertex_groups.get(bone.name)
        if group and any(g.group == group.index and g.weight >= .25 for g in vertex.groups):
            points.append(point)
    if not points: c.fail('MISSING_CAPABILITY','Foot has no measurable weighted skin for a sole reference')
    low = min(p.dot(up) for p in points)
    support = [p for p in points if p.dot(up) <= low+.003]
    return sum(support,Vector())/len(support)


def calibrate_joint_frames(handle, *, avatar_id=None, source_revision='unversioned', recorded_at):
    """Read bind data without zeroing pose, changing a rest bone or evaluating an action.

    Returns schema-v1 AvatarProfile, calibration version 1. Required provenance is explicit.
    """
    bones = _bones(handle)
    inspection = inspect_capabilities(handle)
    scale = handle.rig.matrix_world.to_scale()
    if min(scale) <= 0 or max(scale)-min(scale) > max(scale)*1e-4 or handle.rig.matrix_world.determinant() <= 0:
        c.fail('MISSING_CAPABILITY','Calibration supports positive uniform rig scale only')
    basis = _character_basis(handle)
    right,forward,up = (basis.col[i].copy() for i in range(3))
    points = [p for _,_,p in _rest_skin(handle)]
    if not points: c.fail('MISSING_CAPABILITY','Calibration needs the existing weighted mesh')
    height = max(p.dot(up) for p in points)-min(p.dot(up) for p in points)
    mapped = _mappings(bones)
    reverse = {bones[name].name:semantic for semantic,name in mapped.items()}
    joint_records, lengths, landmarks = [],[c.LengthSpec('rig.unit',float(scale.x))],[]
    for semantic,name in mapped.items():
        bone = bones[name]
        parent = bone.parent
        while parent is not None and parent.name not in reverse: parent = parent.parent
        parent_id = reverse[parent.name] if parent is not None else None
        origin = _rest_world(handle,parent).translation if parent is not None else _rest_world(handle,bones['Hips']).translation
        transform = _rest_world(handle,bone)
        joint_records.append(c.JointMapping(semantic,parent_id,(bone.name,),
            c.Transform(_tuple(basis.transposed() @ (transform.translation-origin)),
                        _tuple(basis.to_quaternion().conjugated() @ _rotation(transform)),
                        'joint:'+parent_id if parent_id else 'entry_body','metre')))
        length = (handle.rig.matrix_world.to_3x3() @ (bone.bone.tail_local-bone.bone.head_local)).length
        lengths.append(c.LengthSpec(semantic,length))
        landmarks.append(c.Landmark(semantic+'.origin',semantic,(0,0,0),'joint:'+semantic,'metre'))
        landmarks.append(c.Landmark(semantic+'.tip',semantic,
            _tuple(basis.transposed() @ (handle.rig.matrix_world.to_3x3() @ (bone.bone.tail_local-bone.bone.head_local))),
            'joint:'+semantic,'metre'))
    controls,limits,capabilities = [],[],list(inspection.available)
    parents = {j.semantic_id:j.parent_id for j in joint_records}

    def scalar(control_id,joint,axis,minimum,maximum,method,mirror=None,mirror_sign=1):
        parent = parents[joint]
        frame = 'joint:'+parent if parent else 'entry_body'
        capability = 'measure.'+control_id
        capabilities.append(capability)
        controls.append(c.ControlSpec(control_id,'degree','scalar',1,(frame,),joint,capability))
        axis = axis.normalized()
        limits.append(c.JointLimit(control_id,minimum,maximum,0,_tuple(basis.transposed() @ axis),
            mirror,mirror_sign,method,max(minimum,-30),min(maximum,30)))

    for joint in ('head','torso','spine.mid','spine.upper','neck'):
        if joint not in mapped: continue
        for suffix,axis,lo,hi in (('yaw',up,-80,80),('pitch',-right,-60,60),('roll',forward,-45,45)):
            scalar(joint+'.'+suffix,joint,axis,lo,hi,'signed calibrated parent-relative swing/twist',
                   joint+'.'+suffix, -1 if suffix in ('yaw','roll') else 1)
    for side,other in (('Left','Right'),('Right','Left')):
        key,opposite = side.lower(),other.lower()
        upper = _rest_direction(handle,bones[side+'Arm'])
        thigh = _rest_direction(handle,bones[side+'UpLeg'])
        for name,joint,axis,lo,hi,method in (
            ('elbow.flexion','forearm',upper.cross(_project(forward,upper)),-10,145,'signed projected upper/lower segment angle; straight=0'),
            ('knee.flexion','shin',thigh.cross(_project(-forward,thigh)),-10,150,'signed projected upper/lower segment angle; straight=0'),
            ('hip.flexion','thigh',right,-90,120,'signed calibrated parent-relative swing/twist'),
            ('forearm.twist','forearm',_rest_direction(handle,bones[side+'ForeArm'])*(-1 if side=='Left' else 1),-180,180,'parent-relative axial swing/twist; positive supination convention'),
            ('ankle.flexion','ankle',right,-50,45,'signed calibrated parent-relative swing/twist')):
            scalar(key+'.'+name,key+'.'+joint,axis,lo,hi,method,opposite+'.'+name)
        if key+'.toe' in mapped:
            scalar(key+'.toe.flexion',key+'.toe',right,-40,60,'signed calibrated parent-relative swing/twist',
                   opposite+'.toe.flexion' if opposite+'.toe' in mapped else None)
        palm = _palm_reference(handle,bones,side)
        if palm:
            longitudinal,radial,normal = palm
            for suffix,axis,lo,hi in (('flexion',longitudinal.cross(normal),-70,70),
                                      ('deviation',longitudinal.cross(radial),-30,30)):
                scalar(key+'.wrist.'+suffix,key+'.wrist',axis,lo,hi,'signed calibrated parent-relative swing/twist',
                       opposite+'.wrist.'+suffix if 'reference.'+opposite+'.palm' in inspection.available else None)
            for suffix,vector in (('palm.forward',longitudinal),('palm.radial',radial),('palm.normal',normal)):
                landmarks.append(c.Landmark(key+'.'+suffix,key+'.wrist',_tuple(basis.transposed() @ vector*.05),
                                             'joint:'+key+'.wrist','metre'))
        foot = bones[side+'Foot']
        sole = _sole_anchor(handle,foot,up)
        for suffix,vector in (('sole.normal',-up),('sole.forward',_project(_rest_direction(handle,foot),up))):
            landmarks.append(c.Landmark(key+'.'+suffix,key+'.ankle',_tuple(basis.transposed() @ vector*.05),
                                         'joint:'+key+'.ankle','metre'))
        landmarks.append(c.Landmark(key+'.sole',key+'.ankle',
            _tuple(basis.transposed() @ (sole-_rest_world(handle,foot).translation)),'joint:'+key+'.ankle','metre'))
        for joint,direction in (('forearm',-forward),('shin',forward)):
            landmarks.append(c.Landmark(key+'.'+joint+'.pole',parents[key+'.'+joint],
                _tuple(basis.transposed() @ direction*.25*height),
                'joint:'+parents[key+'.'+joint],'metre'))
        for segment in ('upper_arm','forearm','thigh','shin'):
            control=key+'.'+segment+'.direction'
            capabilities.append('measure.'+control)
            controls.append(c.ControlSpec(control,'unitless','vector',3,('world',),key+'.'+segment,'measure.'+control))
        for endpoint,joint in (('hand','wrist'),('foot','ankle')):
            for suffix,unit,shape,dimension in (('position','metre','vector',3),('direction','unitless','vector',3),
                                                ('orientation','unitless','quaternion',4)):
                if endpoint=='hand' and suffix=='orientation' and palm is None: continue
                control = f'{key}.{endpoint}.{suffix}'
                capabilities.append('measure.'+control)
                controls.append(c.ControlSpec(control,unit,shape,dimension,('world',),key+'.'+joint,'measure.'+control))
    for suffix,unit,shape,dimension in (('position','metre','vector',3),('orientation','unitless','quaternion',4)):
        control = 'root.'+suffix
        capabilities.append('measure.'+control)
        controls.append(c.ControlSpec(control,unit,shape,dimension,('world',),'pelvis','measure.'+control))
    for axis,index in (('right',0),('forward',1),('up',2)):
        vector = [0,0,0]; vector[index] = .1
        landmarks.append(c.Landmark('character.'+axis,'pelvis',tuple(vector),'joint:pelvis','metre'))
    fingerprint = _fingerprint(handle)
    evidence = ('rig_sha256:'+fingerprint,
                'angles_tolerance_deg:0.1','position_tolerance_m:0.0001',
                'software_ranges:engineering_bounds_not_medical_or_collision_certification',
                'optional_bones:detected_not_created',
                'poles:parent_relative_fallback_below_0.5deg_smooth_blend_to_5deg',
                'palm_reference:'+('procedural_convention' if _procedural(handle) else 'index_pinky_plane_or_unavailable'))
    return c.AvatarProfile(avatar_id or 'rig.'+fingerprint[:16],CALIBRATION_VERSION,height,
        ('world','entry_body','current_root','current_torso','current_pelvis')+tuple('joint:'+j for j in mapped),
        tuple(joint_records),tuple(lengths),tuple(landmarks),tuple(limits),tuple(controls),
        tuple(sorted(set(capabilities))),
        c.Provenance('rest-skeleton and weighted-skin calibration v1; no anatomy edits',source_revision,evidence,recorded_at))


def _joint(handle,profile,joint_id):
    mapping = next((j for j in profile.rest_to_semantic_mappings if j.semantic_id==joint_id),None)
    if mapping is None: c.fail('UNKNOWN_ID','Unknown calibrated joint',details={'joint_id':joint_id})
    bone = handle.rig.pose.bones.get(mapping.source_bones[0])
    if bone is None: c.fail('ENTRY_MISMATCH','Calibrated bone is unavailable')
    return mapping,bone


def semantic_frame(handle,profile,joint_id):
    """World transform of the current anatomical frame (bind axes are character axes)."""
    _binding(handle,profile)
    _,bone = _joint(handle,profile,joint_id)
    rotation = _rotation(_pose_world(handle,bone)) @ _rotation(_rest_world(handle,bone)).conjugated()
    rotation = rotation @ _character_basis(handle).to_quaternion()
    result = rotation.to_matrix().to_4x4()
    result.translation = _pose_world(handle,bone).translation
    return result


def measure_joint_angle(handle,profile,control_id):
    _binding(handle,profile)
    control = next((v for v in profile.controls if v.id==control_id and v.value_shape=='scalar'),None)
    limit = next((v for v in profile.joint_limits if v.control_id==control_id),None)
    if control is None or limit is None: c.fail('MISSING_CAPABILITY','Joint quantity is not calibrated',control_id=control_id)
    mapping,bone = _joint(handle,profile,control.chain)
    parent_frame = semantic_frame(handle,profile,mapping.parent_id) if mapping.parent_id else _character_basis(handle).to_4x4()
    axis = Vector(limit.positive_axis)
    if control_id.endswith(('elbow.flexion','knee.flexion')):
        parent = _joint(handle,profile,mapping.parent_id)[1]
        upper = handle.rig.matrix_world.to_3x3() @ (parent.tail-parent.head)
        lower = handle.rig.matrix_world.to_3x3() @ (bone.tail-bone.head)
        world_axis = parent_frame.to_3x3() @ axis
        first,second = _project(upper,world_axis),_project(lower,world_axis)
        return math.degrees(math.atan2(world_axis.dot(first.cross(second)),first.dot(second)))
    current = _rotation(parent_frame).conjugated() @ _rotation(_pose_world(handle,bone))
    delta = current @ Quaternion(mapping.rest_to_semantic.orientation).conjugated()
    if delta.w < 0: delta.negate()
    projection = Vector((delta.x,delta.y,delta.z)).dot(axis)
    if abs(delta.w)+abs(projection) < 1e-8:
        c.fail('ENTRY_MISMATCH','Swing/twist is singular at this orientation',control_id=control_id)
    return math.degrees(2*math.atan2(projection,delta.w))


def measure_endpoint(handle,profile,endpoint_id):
    """Actual solved bone-head or calibrated sole position, in world metres."""
    _binding(handle,profile)
    c.check_type(endpoint_id,c.ID,'endpoint_id')
    if endpoint_id.endswith('.sole'):
        landmark = next((v for v in profile.landmarks if v.id==endpoint_id),None)
        if landmark is None: c.fail('MISSING_CAPABILITY','Sole reference unavailable')
        return _tuple(semantic_frame(handle,profile,landmark.joint_id) @ Vector(landmark.position))
    key,part = endpoint_id.split('.') if endpoint_id.count('.')==1 else ('','')
    joint = {'hand':'wrist','foot':'ankle'}.get(part)
    if key not in ('left','right') or joint is None: c.fail('UNKNOWN_ID','Unknown endpoint')
    return _tuple(_pose_world(handle,_joint(handle,profile,key+'.'+joint)[1]).translation)


def measure_orientation(handle,profile,endpoint_id):
    """Quaternion with +Y longitudinal, +Z outward palm/sole normal; world-framed."""
    _binding(handle,profile)
    c.check_type(endpoint_id,c.ID,'endpoint_id')
    if endpoint_id.count('.')!=1: c.fail('UNKNOWN_ID','Unknown orientation endpoint')
    side,part = endpoint_id.split('.')
    prefix = 'palm' if part=='hand' else 'sole' if part=='foot' else None
    if side not in ('left','right') or prefix is None: c.fail('UNKNOWN_ID','Unknown orientation endpoint')
    references = {v.id:v for v in profile.landmarks}
    normal = references.get(side+'.'+prefix+'.normal')
    longitudinal = references.get(side+'.'+prefix+'.forward')
    if normal is None or longitudinal is None: c.fail('MISSING_CAPABILITY','Orientation reference is unavailable')
    frame = semantic_frame(handle,profile,normal.joint_id).to_3x3()
    z = (frame @ Vector(normal.position)).normalized()
    y = _project(frame @ Vector(longitudinal.position),z)
    x = y.cross(z).normalized()
    return _tuple(Matrix((x,y,z)).transposed().to_quaternion().normalized())


def measure_bend_plane(handle,profile,limb_id):
    """World pole direction with a stable parent-relative fallback near straight."""
    _binding(handle,profile)
    landmark_id = limb_id+'.pole'
    landmark = next((v for v in profile.landmarks if v.id==landmark_id),None)
    if landmark is None: c.fail('UNKNOWN_ID','Unknown calibrated limb')
    _,lower = _joint(handle,profile,limb_id)
    parent = _joint(handle,profile,landmark.joint_id)[1]
    origin = handle.rig.matrix_world @ parent.head
    elbow = handle.rig.matrix_world @ lower.head
    tip = handle.rig.matrix_world @ lower.tail
    chain = (tip-origin).normalized()
    bend = elbow-origin-chain*(elbow-origin).dot(chain)
    side,segment = limb_id.split('.')
    angle = abs(measure_joint_angle(handle,profile,side+('.elbow.flexion' if segment=='forearm' else '.knee.flexion')))
    reference = semantic_frame(handle,profile,landmark.joint_id).to_3x3() @ Vector(landmark.position)
    reference = _project(reference,chain)
    if angle < POLE_STRAIGHT_THRESHOLD_DEG or bend.length < 1e-7:
        return _tuple(reference)
    measured = bend.normalized()
    # A bend plane has two equivalent signs. Keep its pole in the calibrated
    # hemisphere, including small hyperextension and asymmetric bind offsets.
    if measured.dot(reference)<0: measured.negate()
    weight = min(1,(angle-POLE_STRAIGHT_THRESHOLD_DEG)/(POLE_FULL_MEASUREMENT_DEG-POLE_STRAIGHT_THRESHOLD_DEG))
    weight = weight*weight*(3-2*weight)
    return _tuple(reference.lerp(measured,weight).normalized())


def capture_motion_state(handle,profile,*,revision,captured_time_s=None,contact_anchors=(),active_contacts=()):
    """Read current solved state. Contacts are caller-asserted, never inferred from targets."""
    _binding(handle,profile)
    bpy.context.view_layer.update()
    root = semantic_frame(handle,profile,'pelvis')
    values = []
    for control in profile.controls:
        if control.value_shape=='scalar':
            value = measure_joint_angle(handle,profile,control.id)
        elif control.id.startswith('root.'):
            value = _tuple(root.translation) if control.id.endswith('.position') else _tuple(_rotation(root))
        else:
            endpoint,suffix = control.id.rsplit('.',1)
            if suffix=='position': value = measure_endpoint(handle,profile,endpoint)
            elif suffix=='orientation': value = measure_orientation(handle,profile,endpoint)
            else:
                bone = _joint(handle,profile,control.chain)[1]
                value = _tuple((handle.rig.matrix_world.to_3x3() @ (bone.tail-bone.head)).normalized())
        values.append(c.ControlValue(control.id,control.unit,control.frames[0],value))
    if captured_time_s is None:
        scene = handle.scene
        captured_time_s = (scene.frame_current+scene.frame_subframe-scene.frame_start)/(scene.render.fps/scene.render.fps_base)
    snapshot = c.MotionStateSnapshot(profile.avatar_id,profile.version,revision,captured_time_s,
        c.Transform(_tuple(root.translation),_tuple(_rotation(root)),'world','metre'),
        tuple(values),contact_anchors,active_contacts,velocities=None,phase=None)
    # Measurements outside an engineering envelope remain an explicit entry failure,
    # rather than being clamped to a requested or fabricated pose.
    return validate_snapshot(snapshot,profile)
