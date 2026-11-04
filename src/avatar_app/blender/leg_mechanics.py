"""Profile-7 leg application through FragmentAdapter, not a baking loop."""
import math
import bpy
from mathutils import Vector,Quaternion
from . import rig_profile as rp
from .hand_mechanics import rotate_bone
from .kinematics import solve_leg
from ..movement_library import contracts as c


def apply(adapter,requested):
    h,p=adapter.handle,adapter.profile
    for side in ('left','right'):
        keys=[key for key in requested if key.startswith(side+'.') and
              any(part in key for part in ('.hip.','.knee.','.foot.'))]
        if not keys:continue
        for part in ('UpLeg','Leg','Foot'):
            bone=h.bones[side.title()+part];bone.matrix_basis=adapter.arm_entry_basis[bone.name]
        bpy.context.view_layer.update()
        hipkeys=[key for key in keys if '.hip.' in key]
        endpoint=side+'.foot.position';plane=side+'.knee.plane';flexion=side+'.knee.flexion'
        if endpoint in requested or plane in requested:
            if hipkeys or flexion in requested:
                c.fail('CONSTRAINT_CONFLICT','Hard foot IK and independent hip/knee angles need compatible resolved ownership')
            target=Vector(requested.get(endpoint,rp.measure_endpoint(h,p,side+'.foot')))
            hip=h.rig.matrix_world @ h.bones[side.title()+'UpLeg'].head
            ankle=h.rig.matrix_world @ h.bones[side.title()+'Foot'].head
            a,b=(next(x.value_m for x in p.lengths if x.id==side+'.'+part) for part in ('thigh','shin'))
            distance=(target-hip).length
            if distance> a+b+1e-5 or distance<=abs(a-b)+1e-5:
                c.fail('INVALID_PARAMETER','Foot target is unreachable',control_id=endpoint)
            chain=(target-hip).normalized()
            if plane in requested:
                if rp.measure_joint_angle(h,p,flexion)<3:c.fail('ENTRY_MISMATCH','Knee plane undefined near extension')
                pole=Quaternion(chain,math.radians(requested[plane])) @ rp.knee_plane_reference(h,p,chain)
            else:
                # Preserve the captured anatomical bend-plane angle as the
                # endpoint axis changes. Re-projecting the old knee point can
                # magnify a tiny bind offset into a lateral knee swing.
                entry={x.control_id:x.value for x in adapter.motion.entry_snapshot.measured_controls}
                pole=Quaternion(chain,math.radians(entry[plane])) @ rp.knee_plane_reference(h,p,chain)
            if (target-ankle).length>1e-7 or plane in requested:
                try:solve_leg(h,side.title(),h.rig.matrix_world.inverted() @ target,
                              pole=h.rig.matrix_world.inverted().to_3x3() @ pole.normalized())
                except ValueError:c.fail('INVALID_PARAMETER','Degenerate/unreachable free-leg solve',control_id=endpoint)
        else:
            if hipkeys:adapter._angular(side+'.thigh',requested)
            if flexion in requested:
                upper,lower=(h.bones[side.title()+part] for part in ('UpLeg','Leg'))
                world=h.rig.matrix_world.to_3x3();a=world @ (upper.tail-upper.head);b=world @ (lower.tail-lower.head)
                reference=rp.semantic_frame(h,p,side+'.thigh').to_3x3() @ Vector(adapter.limits[flexion].positive_axis)
                axis=a.cross(b)
                if axis.length<1e-6 or axis.dot(reference)<0:axis=reference
                axis.normalize();signed=math.degrees(math.atan2(axis.dot(a.cross(b)),a.dot(b)))
                rotate_bone(adapter,side+'.shin',Quaternion(axis,math.radians(requested[flexion]-signed)))
        orientation=side+'.foot.orientation'
        if orientation in requested:
            current=Quaternion(rp.measure_orientation(h,p,side+'.foot'))
            rotate_bone(adapter,side+'.ankle',Quaternion(requested[orientation]) @ current.conjugated())
        for suffix in ('hip.flexion','hip.abduction','hip.rotation','knee.flexion','ankle.flexion'):
            key=side+'.'+suffix;limit=adapter.limits[key];actual=rp.measure_joint_angle(h,p,key)
            if not limit.minimum<=actual<=limit.maximum:
                c.fail('INVALID_PARAMETER','Leg solve exceeds a calibrated joint bound',control_id=key,
                       details={'actual_deg':actual,'minimum_deg':limit.minimum,'maximum_deg':limit.maximum,
                                'foot_target':requested.get(endpoint),'knee_flexion_deg':rp.measure_joint_angle(h,p,flexion),
                                'leg_points':[tuple(h.rig.matrix_world @ h.bones[side.title()+part].head) for part in ('UpLeg','Leg','Foot')]})


def clearance(adapter):
    """Capsule clearance between leg segments, excluding the adjacent hip joint."""
    from ..movement_library.curves import segment_distance
    h,p=adapter.handle,adapter.profile;points={}
    for side in ('left','right'):
        points[side]=[h.rig.matrix_world @ h.bones[side.title()+part].head for part in ('UpLeg','Leg','Foot')]
    minimum=float('inf')
    for i,(a,b) in enumerate(zip(points['left'],points['left'][1:])):
        for j,(d,e) in enumerate(zip(points['right'],points['right'][1:])):
            # Thighs naturally meet at the pelvis; review their distal 80%.
            first=a.lerp(b,.2) if i==0 else a;second=d.lerp(e,.2) if j==0 else d
            minimum=min(minimum,segment_distance(first,b,second,e)-.048*p.height_m)
    return minimum
