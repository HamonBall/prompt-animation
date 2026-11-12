"""Calibrate and apply fixed palm support without changing existing rig profiles."""
from dataclasses import replace
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

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


def place_crawl_knees(handle, profile, targets, floor):
    """Fit pelvis height and roll to two knee points while keeping both shanks oriented."""
    from .kinematics import aim

    world = handle.rig.matrix_world
    inverse = world.inverted()
    hips = handle.bones['Hips']
    base = world @ hips.matrix
    pivot = base.translation
    heading = rp.semantic_frame(handle, profile, 'pelvis').to_3x3().col[2].copy()
    heading.z = 0
    heading.normalize()
    legs = []
    for anchor, goal in targets:
        side = anchor.split('.')[0].title()
        upper, lower = (handle.bones[side + part] for part in ('UpLeg', 'Leg'))
        hip, knee = world @ upper.head, world @ lower.head
        skin = body_contact_point(handle, profile, anchor, floor)
        legs.append((anchor, upper, lower, hip - pivot, (knee - hip).length,
                     lower.matrix.to_quaternion().copy(), Vector(goal), Vector(goal) + knee - skin))

    height, roll = 0., 0.
    for _ in range(7):
        for _ in range(8):
            rotation = Quaternion(heading, roll)
            equations = []
            for _, _, _, offset, length, _, _, knee in legs:
                offset = rotation @ offset
                delta = pivot + offset + Vector((0, 0, height)) - knee
                unit = delta.normalized()
                equations.append((delta.length - length, unit.z, unit.dot(heading.cross(offset))))
            left, right = equations
            if max(abs(left[0]), abs(right[0])) < 1e-6:
                break
            determinant = left[1] * right[2] - right[1] * left[2]
            if abs(determinant) < 1e-6:
                c.fail('ENTRY_MISMATCH', 'Kneeling hips cannot resolve two independent knee heights')
            height -= (left[0] * right[2] - right[0] * left[2]) / determinant
            roll -= (left[1] * right[0] - right[1] * left[0]) / determinant
            if abs(height) > .12 or abs(roll) > .35:
                c.fail('INVALID_PARAMETER', 'Knee crawl needs an unreachable pelvis adjustment',
                       details={'height_m': height, 'roll_deg': math.degrees(roll)})
        rotation = Quaternion(heading, roll)
        hips.matrix = (inverse @ Matrix.Translation(pivot + Vector((0, 0, height)))
                       @ rotation.to_matrix().to_4x4() @ Matrix.Translation(-pivot) @ base)
        bpy.context.view_layer.update()
        worst = 0.
        for anchor, upper, lower, _, _, orientation, goal, knee in legs:
            aim(upper, inverse @ knee - upper.head)
            lower.matrix = Matrix.Translation(lower.head) @ orientation.to_matrix().to_4x4()
            bpy.context.view_layer.update()
            error = goal - body_contact_point(handle, profile, anchor, floor)
            worst = max(worst, error.length)
            knee += error
        if worst < .0005:
            return
    c.fail('INVALID_PARAMETER', 'Knee crawl could not settle the knee contact points',
           details={'error_m': worst})


def apply_crawl_knees(adapter, requested, events, time_s):
    """Resolve both knee contacts before the hand tracks are applied."""
    from .motion import contact_ease
    from ..movement_library.coordinated import KNEE_CRAWL_ANCHORS

    handle, profile = adapter.handle, adapter.profile
    floor = adapter.fixed_surfaces['floor']
    targets = []
    for anchor in KNEE_CRAWL_ANCHORS[2:]:
        reference = Vector(rp.measure_endpoint(handle, profile, anchor))
        skin = body_contact_point(handle, profile, anchor, floor)
        nominal = Vector(requested[anchor + '.position']) + skin - reference
        event = next((event for event in events if event.anchor_id == anchor), None)
        if event is not None:
            acquire = (time_s - event.interval.start_s) / event.acquire_s if event.acquire_s else 1.
            release = (event.interval.end_s - time_s) / event.release_s if event.release_s else 1.
            nominal = nominal.lerp(Vector(event.target_world_v1), contact_ease(min(1., acquire, release)))
        targets.append((anchor, nominal))
    place_crawl_knees(handle, profile, targets, floor)
