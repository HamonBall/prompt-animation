"""Existing-bone finger application inside the shared baking transaction."""
import math
import bpy
from mathutils import Vector,Quaternion,Matrix
from . import rig_profile as rp
from ..movement_library import contracts as c


def apply(adapter,requested):
    h,p=adapter.handle,adapter.profile
    chains={adapter.controls[key].chain for key in requested if '.finger.' in key}
    for chain in sorted(chains,key=lambda key:(sum(1 for _ in adapter._parents(key)),key)):
        mapping=adapter.joints[chain];bone=h.rig.pose.bones[mapping.source_bones[0]]
        keys=[chain+'.curl',chain+'.spread'];available=[key for key in keys if key in adapter.limits]
        a=Vector(adapter.limits[keys[0]].positive_axis)
        # A one-axis interphalangeal joint keeps both unrequested tangent components.
        b=Vector(adapter.limits[keys[1]].positive_axis) if keys[1] in adapter.limits else a.orthogonal().normalized()
        normal=a.cross(b).normalized();axes=Matrix((a,b,normal))
        parent=rp.semantic_frame(h,p,mapping.parent_id).to_quaternion()
        world=h.rig.matrix_world @ bone.matrix
        delta=parent.conjugated() @ world.to_quaternion() @ Quaternion(mapping.rest_to_semantic.orientation).conjugated()
        if abs(delta.w)<1e-5:c.fail('ENTRY_MISMATCH','Finger swing/twist is singular',control_id=keys[0])
        tangent=Vector((delta.x,delta.y,delta.z))/delta.w
        components=[tangent.dot(axis) for axis in (a,b,normal)]
        for index,key in enumerate(keys):
            if key in requested:components[index]=math.tan(math.radians(requested[key])/2)
        vector=axes.inverted() @ Vector(components)
        rotation=parent @ Quaternion((1,*vector)).normalized() @ Quaternion(mapping.rest_to_semantic.orientation)
        bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(world.translation) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
        bpy.context.view_layer.update()
