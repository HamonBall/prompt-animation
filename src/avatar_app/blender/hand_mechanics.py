"""Calibrated v5 hand-chain application, used only by FragmentAdapter."""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector
from . import rig_profile as rp
from .pose import position_hand, axes
from ..movement_library import contracts as c
from ..movement_library.hands import forearm_twist_sign


def rotate_bone(adapter,chain,rotation):
    h=adapter.handle;bone=h.rig.pose.bones[adapter.joints[chain].source_bones[0]]
    world=h.rig.matrix_world @ bone.matrix
    bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(world.translation) @
        (rotation @ world.to_quaternion()).to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
    bpy.context.view_layer.update()


def set_twist(adapter,side,target):
    h,p=adapter.handle,adapter.profile;key=side+'.forearm.twist'
    for _ in range(3):
        error=target-rp.measure_joint_angle(h,p,key)
        if abs(error)<1e-4:return
        lower=h.bones[side.title()+'ForeArm']
        axis=(h.rig.matrix_world.to_3x3() @ (lower.tail-lower.head)).normalized()
        # Calibrated positive supination axis can oppose the segment direction.
        axis*=forearm_twist_sign(p,side)
        rotate_bone(adapter,side+'.forearm',Quaternion(axis,math.radians(error)))


def wrist_angles(adapter,side,requested):
    h,p=adapter.handle,adapter.profile;chain=side+'.wrist'
    mapping=adapter.joints[chain]
    keys=[side+'.wrist.'+name for name in ('flexion','deviation')]
    if not all(key in adapter.limits for key in keys):c.fail('MISSING_CAPABILITY','Palm axes are unavailable')
    a,b=(Vector(adapter.limits[key].positive_axis) for key in keys)
    normal=a.cross(b).normalized();matrix=Matrix((a,b,normal))
    parent=rp.semantic_frame(h,p,mapping.parent_id).to_quaternion()
    bone=h.rig.pose.bones[mapping.source_bones[0]];world=h.rig.matrix_world @ bone.matrix
    delta=parent.conjugated() @ world.to_quaternion() @ Quaternion(mapping.rest_to_semantic.orientation).conjugated()
    tangent=Vector((delta.x,delta.y,delta.z))/delta.w
    values=[math.tan(math.radians(requested.get(key,rp.measure_joint_angle(h,p,key)))/2) for key in keys]
    vector=matrix.inverted() @ Vector((*values,tangent.dot(normal)))
    rotation=parent @ Quaternion((1,*vector)).normalized() @ Quaternion(mapping.rest_to_semantic.orientation)
    bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(world.translation) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
    bpy.context.view_layer.update()


def apply(adapter,requested):
    h,p=adapter.handle,adapter.profile
    requested=dict(requested)
    for side in ('left','right'):
        torso=rp.semantic_frame(h,p,'torso')
        if side+'.hand.torso_position' in requested:
            requested[side+'.hand.position']=tuple(torso @ Vector(requested[side+'.hand.torso_position']))
        if side+'.hand.torso_orientation' in requested:
            requested[side+'.hand.orientation']=tuple(torso.to_quaternion() @ Quaternion(requested[side+'.hand.torso_orientation']))
    for side in ('left','right'):
        key=side+'.elbow.flexion'
        if key in requested:
            twist=rp.measure_joint_angle(h,p,side+'.forearm.twist')
            upper,lower=(h.bones[side.title()+part] for part in ('Arm','ForeArm'))
            world=h.rig.matrix_world.to_3x3()
            a,b=(world @ (bone.tail-bone.head) for bone in (upper,lower))
            axis=a.cross(b)
            if axis.length<1e-6:axis=rp.semantic_frame(h,p,side+'.upper_arm').to_3x3() @ Vector(adapter.limits[key].positive_axis)
            axis.normalize()
            error=requested[key]-rp.measure_joint_angle(h,p,key)
            rotate_bone(adapter,side+'.forearm',Quaternion(axis,math.radians(error)))
            set_twist(adapter,side,twist)
        endpoint=side+'.hand.position';plane=side+'.elbow.plane'
        if endpoint in requested or plane in requested:
            if side+'.upper_arm.orientation' in requested:
                c.fail('CONSTRAINT_CONFLICT','Endpoint IK and a hard upper-arm orientation require pre-resolved compatible ownership')
            # Absolute endpoint goals must not accumulate parallel-transport
            # roll/pole drift from previous samples. Rebase only the declared
            # supporting arm, after its current parent transforms were applied.
            for part in ('Arm','ForeArm','Hand'):
                bone=h.bones[side.title()+part]
                bone.matrix_basis=adapter.arm_entry_basis[bone.name]
            bpy.context.view_layer.update()
            target=Vector(requested.get(endpoint,rp.measure_endpoint(h,p,side+'.hand')))
            adapter._check_reach(endpoint,target)
            shoulder=h.rig.matrix_world @ h.bones[side.title()+'Arm'].head
            elbow=h.rig.matrix_world @ h.bones[side.title()+'ForeArm'].head
            current=Vector(rp.measure_endpoint(h,p,side+'.hand'))
            chain=(target-shoulder).normalized()
            if plane in requested:
                reference=rp.elbow_plane_reference(h,p,chain)
                pole=Quaternion(chain,math.radians(requested[plane])) @ reference
            else:
                pole=elbow-shoulder-chain*(elbow-shoulder).dot(chain)
                if pole.length<1e-6:pole=rp.elbow_plane_reference(h,p,chain)
            if (target-current).length>1e-6 or plane in requested:
                try:
                    position_hand(h,side.title(),h.rig.matrix_world.inverted() @ target,axes(h),
                        pole=h.rig.matrix_world.inverted() @ (shoulder+pole.normalized()*p.height_m))
                except ValueError:
                    c.fail('INVALID_PARAMETER','Hand target is unreachable in the calibrated arm frame',control_id=endpoint)
        if side+'.forearm.twist' in requested:set_twist(adapter,side,requested[side+'.forearm.twist'])
        if any(side+'.wrist.'+suffix in requested for suffix in ('flexion','deviation')):
            wrist_angles(adapter,side,requested)
        orientation=side+'.hand.orientation'
        if orientation in requested:
            if any(side+'.wrist.'+suffix in requested for suffix in ('flexion','deviation')) or side+'.forearm.twist' in requested:
                c.fail('CONSTRAINT_CONFLICT','Explicit palm orientation conflicts with independent wrist/forearm controls')
            desired=Quaternion(requested[orientation]);current=Quaternion(rp.measure_orientation(h,p,side+'.hand'))
            delta=desired @ current.conjugated()
            if delta.x*delta.x+delta.y*delta.y+delta.z*delta.z<1e-12:continue
            lower=h.bones[side.title()+'ForeArm'];axis=(h.rig.matrix_world.to_3x3() @ (lower.tail-lower.head)).normalized()
            axial=Vector((delta.x,delta.y,delta.z)).dot(axis)
            twist=Quaternion((delta.w,*(axis*axial)))
            if twist.magnitude>1e-6:
                twist.normalize();rotate_bone(adapter,side+'.forearm',twist)
            current=Quaternion(rp.measure_orientation(h,p,side+'.hand'))
            rotate_bone(adapter,side+'.wrist',desired @ current.conjugated())
