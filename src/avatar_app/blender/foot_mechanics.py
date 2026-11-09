"""Calibrated rigid-foot references and profile-8 local articulation."""
from dataclasses import replace
import math

from mathutils import Quaternion, Vector

from ..movement_library import contracts as c
from ..movement_library.feet import MARKER, POINTS
from ..movement_library.legs import with_legs_v1
from . import rig_profile as rp
from .hand_mechanics import rotate_bone


def calibrate_feet(handle, profile):
    """Extend the bound leg profile using its existing weighted bind geometry."""
    rp._binding(handle, profile)
    if profile.version == 8:
        return profile
    profile = with_legs_v1(profile)
    basis = rp._character_basis(handle)
    landmarks = {item.id: item for item in profile.landmarks}
    added = []
    controls = []
    limits = []
    for side, opposite, sign in (('left', 'right', 1), ('right', 'left', -1)):
        ankle = f'{side}.ankle'
        _, foot = rp._joint(handle, profile, ankle)
        origin = rp._rest_world(handle, foot).translation
        forward = basis @ Vector(landmarks[f'{side}.sole.forward'].position).normalized()
        sole = Vector(landmarks[f'{side}.sole'].position)
        up = basis.col[2]
        # Measure the longitudinal footprint from the low part of the skin.
        # A toe bone may contribute geometry but never owns either contact.
        bone_names = {foot.name}
        bone_names.update(mapping.source_bones[0] for mapping in profile.rest_to_semantic_mappings
                          if mapping.semantic_id == f'{side}.toe')
        samples = []
        for obj, vertex, point in rp._rest_skin(handle):
            groups = {obj.vertex_groups[name].index for name in bone_names if name in obj.vertex_groups}
            if sum(g.weight for g in vertex.groups if g.group in groups) >= .25:
                samples.append(point - origin)
        if not samples:
            c.fail('MISSING_CAPABILITY', 'Foot contact needs weighted foot geometry', control_id=ankle)
        low = min(point.dot(up) for point in samples)
        floor_points = [point for point in samples if point.dot(up) <= low + .008]
        extent = [point.dot(forward) for point in floor_points]
        if max(extent) - min(extent) < .02:
            c.fail('MISSING_CAPABILITY', 'Foot contact geometry has no heel-to-forefoot extent', control_id=ankle)
        local_forward = basis.transposed() @ forward
        for name, longitudinal in (('heel', min(extent)), ('forefoot', max(extent))):
            point = sole + local_forward * (longitudinal - sole.dot(local_forward))
            added.append(c.Landmark(f'{side}.{name}', ankle, tuple(point), 'joint:' + ankle, 'metre'))
        for name in POINTS:
            key = f'{side}.{name}.position'
            controls.append(c.ControlSpec(key, 'metre', 'vector', 3, ('world',), ankle, 'measure.' + key))
        key = f'{side}.ankle.tilt'
        controls.append(c.ControlSpec(key, 'degree', 'scalar', 1, ('joint:' + side + '.shin',), ankle, 'measure.' + key))
        limits.append(c.JointLimit(key, -25, 25, 0, (0, sign, 0), f'{opposite}.ankle.tilt', 1,
                                   'signed calibrated parent-relative swing/twist', -15, 15))
    return replace(
        profile, version=8, landmarks=profile.landmarks + tuple(added),
        controls=profile.controls + tuple(controls), joint_limits=profile.joint_limits + tuple(limits),
        capabilities=tuple(sorted(set(profile.capabilities) | {item.capability for item in controls})),
        calibration_provenance=replace(profile.calibration_provenance,
                                       evidence=profile.calibration_provenance.evidence + (MARKER,)),
    )


def apply_local(adapter, requested):
    """Set local swing/twist projections, preserving every unrequested component."""
    h, profile = adapter.handle, adapter.profile
    for side in ('left', 'right'):
        for chain, suffixes in (('ankle', ('ankle.flexion', 'ankle.tilt')), ('toe', ('toe.flexion',))):
            keys = [f'{side}.{suffix}' for suffix in suffixes if f'{side}.{suffix}' in requested]
            if not keys:
                continue
            joint = f'{side}.{chain}'
            mapping, bone = rp._joint(h, profile, joint)
            parent = rp.semantic_frame(h, profile, mapping.parent_id).to_quaternion()
            current = rp._pose_world(h, bone).to_quaternion()
            rest = Quaternion(mapping.rest_to_semantic.orientation)
            delta = parent.conjugated() @ current @ rest.conjugated()
            if abs(delta.w) < 1e-7:
                c.fail('ENTRY_MISMATCH', 'Local foot orientation is singular', control_id=keys[0])
            tangent = Vector((delta.x, delta.y, delta.z)) / delta.w
            for key in keys:
                axis = Vector(adapter.limits[key].positive_axis)
                tangent += axis * (math.tan(math.radians(requested[key]) / 2) - tangent.dot(axis))
            desired = parent @ Quaternion((1, *tangent)).normalized() @ rest
            rotate_bone(adapter, joint, desired @ current.conjugated())


def apply_pivots(adapter, requested, contacts):
    """Convert a fixed contact and sampled foot orientation into an IK target."""
    h, profile = adapter.handle, adapter.profile
    solved = dict(requested)
    for event in contacts:
        side, anchor = event.anchor_id.split('.')
        if anchor not in ('heel', 'forefoot'):
            continue
        orientation = f'{side}.foot.orientation'
        endpoint = f'{side}.foot.position'
        current = Quaternion(rp.measure_orientation(h, profile, side + '.foot'))
        desired = Quaternion(requested[orientation])
        ankle = Vector(rp.measure_endpoint(h, profile, side + '.foot'))
        point = Vector(rp.measure_endpoint(h, profile, event.anchor_id))
        target = adapter.anchors[event.anchor_id] - (desired @ current.conjugated()) @ (point - ankle)
        if endpoint in solved and (target - Vector(solved[endpoint])).length > .001:
            c.fail('CONSTRAINT_CONFLICT', 'Overlapping foot pivots disagree', control_id=endpoint)
        solved[endpoint] = tuple(target)
    return solved
