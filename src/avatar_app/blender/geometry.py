"""Extrema of evaluated skin, avoiding rotated bounding-box corner overestimates."""
import numpy as np
import bpy
from mathutils import Vector
from ..models import PlanError


def mesh_points(obj, graph):
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh()
    try:
        points = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get('co', points)
        matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
        world = points.reshape((-1, 3)) @ matrix[:3, :3].T + matrix[:3, 3]
        if not np.isfinite(world).all():
            raise PlanError('The avatar has nonfinite skin geometry. Previous animation kept.')
        return world
    finally:
        evaluated.to_mesh_clear()


def pose_meshes(handle):
    # Several constraints inspect the same evaluated skin in a frame. Reuse it
    # until an actual bone/object transform changes; never cache across poses.
    objects = [obj for obj in handle.objects if obj.type == 'MESH']
    if not getattr(handle, '_skin_cache_enabled', False):
        graph = bpy.context.evaluated_depsgraph_get()
        return [(obj, mesh_points(obj, graph)) for obj in objects]
    signature = (handle.scene.frame_current,
                 tuple(tuple(v for row in b.matrix_basis for v in row) for b in handle.rig.pose.bones),
                 tuple(tuple(v for row in obj.matrix_world for v in row) for obj in objects))
    if getattr(handle, '_skin_signature', None) != signature:
        graph = bpy.context.evaluated_depsgraph_get()
        handle._skin_points = [(obj, mesh_points(obj, graph)) for obj in objects]
        handle._skin_signature = signature
    return handle._skin_points


def skin_bounds(handle):
    bounds = [(p.min(axis=0), p.max(axis=0)) for obj, p in pose_meshes(handle) if len(p)]
    return Vector(np.min([p[0] for p in bounds], axis=0)), Vector(np.max([p[1] for p in bounds], axis=0))


def rest_foot_rear(handle, origin, forward):
    """Rear extent of bind-pose footwear, independent of the displayed action."""
    minimum = float('inf')
    for obj in handle.objects:
        if obj.type != 'MESH':
            continue
        groups = {g.index for g in obj.vertex_groups
                  if any(g.name.endswith(side+part) for side in ('Left', 'Right')
                         for part in ('Foot', 'ToeBase'))}
        for v in obj.data.vertices:
            if any(g.group in groups and g.weight > .2 for g in v.groups):
                minimum = min(minimum, ((obj.matrix_world @ v.co)-origin).dot(forward))
    return minimum


def seat_penetration(handle, surface):
    if surface.center is None:
        return 0.0
    worst = 0.0
    for obj, p in pose_meshes(handle):
        mask = ((abs(p[:, 0]-surface.center[0]) < surface.size[0]/2-.001)
                & (abs(p[:, 1]-surface.center[1]) < surface.size[1]/2-.001)
                & (p[:, 2] > surface.height-.15))
        if mask.any():
            worst = max(worst, surface.height-float(p[mask, 2].min()))
    return worst


def support_floor(handle):
    """Torso/head/leg skin envelope, independent of a hand being acquired."""
    cache = getattr(handle, '_support_masks', {})
    handle._support_masks = cache
    minimum = float('inf')
    for obj, p in pose_meshes(handle):
        if obj.name not in cache:
            excluded = {group.index for group in obj.vertex_groups
                        if any(word in group.name.lower() for word in ('arm', 'hand', 'shoulder'))}
            mask = []
            for vertex in obj.data.vertices:
                strongest = max(vertex.groups, key=lambda g: g.weight, default=None)
                mask.append(strongest is None or strongest.group not in excluded)
            cache[obj.name] = np.asarray(mask, dtype=bool)
        mask = cache[obj.name]
        if len(mask) == len(p) and mask.any():
            minimum = min(minimum, float(p[mask, 2].min()))
    return minimum


def support_skin_height(handle, part, surface=None, offset_xy=(0, 0)):
    hand = part in ('left_hand', 'right_hand')
    names = ((part.split('_')[0].title()+'Hand',) if hand else
             ('Hips', 'LeftUpLeg', 'RightUpLeg') if part == 'pelvis' else ('Spine', 'Spine1', 'Spine2', 'Hips'))
    accepted = {handle.bones[n].name for n in names if n in handle.bones}
    anchor_name = names[0] if hand else 'Hips' if part == 'pelvis' else 'Spine'
    anchor = np.asarray(handle.rig.matrix_world @ handle.bones[anchor_name].head)
    height = (handle.rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
    cache = getattr(handle, '_part_masks', {})
    handle._part_masks = cache
    minimum = float('inf')
    for obj, p in pose_meshes(handle):
        key = obj.name, part
        if key not in cache:
            indices = {g.index for g in obj.vertex_groups if g.name in accepted
                       or (hand and any(g.name.startswith(name) for name in accepted))}
            cache[key] = np.asarray([any(g.group in indices and g.weight > .2 for g in v.groups)
                                     for v in obj.data.vertices], dtype=bool)
        mask = cache[key]
        if len(mask) != len(p):
            continue
        local = mask & (np.linalg.norm(p-anchor, axis=1) < height*.20)
        if surface is not None and surface.center is not None:
            local &= ((abs(p[:,0]+offset_xy[0]-surface.center[0]) <= surface.size[0]/2)
                      & (abs(p[:,1]+offset_xy[1]-surface.center[1]) <= surface.size[1]/2))
        if local.any():
            minimum = min(minimum, float(p[local, 2].min()))
    return minimum
