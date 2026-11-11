"""Calibrate and apply fixed palm support without changing existing rig profiles."""
from dataclasses import replace
import math

import bpy
from mathutils import Quaternion, Vector

from . import rig_profile as rp
from .hand_mechanics import rotate_bone
from .geometry import support_skin_height
from .pose import axes, position_hand
from ..movement_library import contracts as c
from ..movement_library.spatial import palm_rotation

MARKER = 'support_contacts_v1:weighted_skin_points'


def support_part(anchor):
    side = anchor.split('.')[0]
    if anchor.endswith('.palm'):
        return side + '_hand'
    if anchor.endswith('.knee.support'):
        return side + '_knee'
    return side


def body_contact_point(handle, profile, anchor, surface, *, offset_xy=(0, 0)):
    """Use the calibrated horizontal reference and the evaluated skin height."""
    position = Vector(rp.measure_endpoint(handle, profile, anchor))
    position.z = support_skin_height(handle, support_part(anchor), surface, offset_xy)
    if not math.isfinite(position.z):
        c.fail('ENTRY_MISMATCH', 'No contact skin lies over the resolved surface',
               details={'anchor_id': anchor, 'surface_id': surface.name})
    return position


def calibrate_support(handle, profile):
    rp._binding(handle, profile)
    if profile.version != 8:
        c.fail('VERSION_MISMATCH', 'Skin support extends the profile-8 contact calibration')
    if MARKER in profile.calibration_provenance.evidence:
        return profile
    landmarks = {item.id: item for item in profile.landmarks}
    basis = rp._character_basis(handle)
    points = []
    controls = []
    references = [
        ('pelvis.support', 'pelvis', -basis.col[2], ('pelvis', 'left.thigh', 'right.thigh'), .13),
        ('back.support', 'torso', -basis.col[1], ('torso', 'spine.mid', 'spine.upper'), .13),
    ]
    for side in ('left', 'right'):
        references.append((side + '.knee.support', side + '.shin', basis.col[1],
                           (side + '.shin', side + '.thigh'), .055))
        name = side + '.palm'
        if name + '.normal' in landmarks:
            normal = (basis @ Vector(landmarks[name + '.normal'].position)).normalized()
            references.append((name, side + '.wrist', normal, (side + '.wrist',), .20))
    mappings = {item.semantic_id: item.source_bones[0] for item in profile.rest_to_semantic_mappings}
    skin = list(rp._rest_skin(handle))
    for name, chain, normal, chains, radius in references:
        _, bone = rp._joint(handle, profile, chain)
        origin = rp._rest_world(handle, bone).translation
        names = {mappings[item] for item in chains if item in mappings}
        palm = name.endswith('.palm')
        group_indices = {}
        for obj in handle.objects:
            if obj.type == 'MESH':
                group_indices[obj.name] = {group.index for group in obj.vertex_groups
                                           if group.name in names or (palm and group.name.startswith(bone.name))}
        samples = []
        for obj, vertex, point in skin:
            offset = point - origin
            if offset.length <= profile.height_m * radius and any(
                    weight.group in group_indices[obj.name] and weight.weight > .2 for weight in vertex.groups):
                samples.append(offset)
        if not samples:
            continue
        outer = max(point.dot(normal) for point in samples)
        face = [point for point in samples if point.dot(normal) >= outer - .005]
        midpoint = sum(face, Vector((0, 0, 0))) / len(face)
        midpoint += normal * (outer - midpoint.dot(normal))
        points.append(c.Landmark(name, chain, tuple(basis.transposed() @ midpoint), 'joint:' + chain, 'metre'))
        key = name + '.position'
        controls.append(c.ControlSpec(key, 'metre', 'vector', 3, ('world',), chain, 'measure.' + key))
    return replace(profile, landmarks=profile.landmarks + tuple(points), controls=profile.controls + tuple(controls),
                   capabilities=tuple(sorted(set(profile.capabilities) | {item.capability for item in controls})),
                   calibration_provenance=replace(profile.calibration_provenance,
                                                  evidence=profile.calibration_provenance.evidence + (MARKER,)))


def apply_palm(adapter, side, target, weight):
    """Place the calibrated palm point with its outward normal facing the surface."""
    handle, profile = adapter.handle, adapter.profile
    key = side + '.hand'
    wrist = Vector(rp.measure_endpoint(handle, profile, key))
    palm = Vector(rp.measure_endpoint(handle, profile, side + '.palm'))
    orientation = Quaternion(rp.measure_orientation(handle, profile, key))
    forward = orientation @ Vector((0, 1, 0))
    forward.z = 0
    if forward.length < 1e-5:
        forward = rp.semantic_frame(handle, profile, 'pelvis').to_3x3().col[1].copy()
        forward.z = 0
    desired = orientation.slerp(Quaternion(palm_rotation(tuple(forward), (0, 0, -1))), weight)
    goal = palm.lerp(Vector(target), weight)
    wrist_goal = goal - (desired @ orientation.conjugated()) @ (palm - wrist)
    adapter._check_reach(key + '.position', wrist_goal)
    if (wrist_goal - wrist).length > 1e-6:
        side_title = side.title()
        upper = handle.bones[side_title + 'Arm']
        elbow = handle.bones[side_title + 'ForeArm']
        axis = (handle.rig.matrix_world.inverted() @ wrist_goal - upper.head).normalized()
        bend = elbow.head - upper.head
        pole = elbow.head if (bend - axis * bend.dot(axis)).length > 1e-5 else None
        position_hand(handle, side_title, handle.rig.matrix_world.inverted() @ wrist_goal, axes(handle), pole=pole)
    actual = Quaternion(rp.measure_orientation(handle, profile, key))
    rotate_bone(adapter, side + '.wrist', desired @ actual.conjugated())
    for axis in ('flexion', 'deviation'):
        control = f'{side}.wrist.{axis}'
        measured = rp.measure_joint_angle(handle, profile, control)
        limit = adapter.limits[control]
        if not limit.minimum <= measured <= limit.maximum:
            c.fail('INVALID_PARAMETER', 'Palm support exceeds a calibrated wrist limit', control_id=control,
                   details={'actual_deg': measured, 'weight': weight, 'bounds_deg': (limit.minimum, limit.maximum)})
    return goal
