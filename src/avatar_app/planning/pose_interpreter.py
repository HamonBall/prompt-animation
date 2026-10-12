"""Open-ended pose interpretation using general anatomical controls."""
import json
import re
from ..models import PlanError
from ..pose import LIMITS, PosePlan, serialize_pose, update_pose
from .local_model import get_model


SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['kind', 'changes', 'contact', 'message'],
    'properties': {
        'kind': {'type': 'string', 'enum': ['pose', 'edit', 'clarify', 'unsupported']},
        'changes': {'type': 'object', 'additionalProperties': {'type': ['number', 'string', 'null']}},
        'contact': {'enum': ['auto', 'both', 'left', 'right', 'none', None]},
        'message': {'type': 'string', 'maxLength': 180},
    },
}

# The model speaks anatomical directions; the application owns coordinate signs.
SYSTEM = """Translate any human body pose into JSON: kind, changes, contact, message.
No pose-name whitelist: decompose creative requests into body parts.
kind=pose for a new pose (reset previous controls), edit for a correction
(only change requested parts), clarify for consequential ambiguity, unsupported
only for missing capabilities. For clarify/unsupported: changes={}, contact=null.
message: at most 12 words. Return compact JSON only, never code.

Prefer semantic direction strings for these parts:
left_arm, right_arm (UPPER arm); left_forearm, right_forearm;
left_thigh, right_thigh; left_shin, right_shin.
Directions: down, up, out, forward, backward, across.
Examples: "right_arm":"up", "left_forearm":"out", "right_thigh":"forward:70".
Optional :ANGLE means elevation from hanging down, in degrees. Full forward
or out =90, fully up=180, down=0. Unspecified forearm/shin follows its upper
segment. To bend a raised knee, thigh=forward, shin=down. To bend an elbow
upward with upper arm horizontal, arm=out, forearm=up. Arms relaxed=down,
NOT out. Include both segments when changing a previously explicit pose.

torso, head, root use direction:ANGLE strings. Directions:
forward/backward = bend; left/right = turn; tilt_left/tilt_right = side lean.
Examples: "torso":"forward:60" (a bow), "head":"left:45" (look left),
"root":"backward:90" (lie on back). Several axes may be combined with commas,
e.g. "torso":"forward:30,tilt_left:15". Default angle=30 for these three parts.
root rotates WHOLE body; torso bends at the waist; head is relative to torso.
All limb directions are relative to whole-body axes, so relaxed arms point
down independently of torso bending. Avatar's own left/right, not viewer's.

Numeric offsets: pelvis_drop downward / avatar height (-.3.. .65);
pelvis_forward, pelvis_side (-.75.. .75), side positive right; duration (.5..8)
seconds. Standing defaults: all offsets 0, duration 2, arms down.
grounding defaults to 1: free poses are automatically settled onto the floor.
For intentionally airborne/floating poses set grounding=0 and use a negative
pelvis_drop to raise the whole body. Floor penetration is still corrected.
Sitting: thighs forward, shins down, pelvis_drop .25, contact=none.
Kneeling: thighs down, shins backward, pelvis_drop .25, contact=none.
Lying on back: root backward:90, pelvis_drop .45, contact=none.
These are examples, not a restriction on creative pose requests.

Hand-on-body poses can use wrist targets instead of arm directions:
left_hand_target_side/forward/height, right_hand_target_side/forward/height.
Give all THREE numeric coordinates relative to pelvis, in body axes, as
fractions of avatar height (-.8.. .8 each). Positive side=right, height=up.
Right salute: side .08, forward .09, height .40. Left salute: side -.08.
Hands on hips: sides +/-.12, forward .03, height .02. Hands behind head:
sides +/-.12, forward -.04, height .35. Across chest: opposite side +/-.08,
forward .12, height .25. Wrist targets override arm directions.
When releasing a wrist target, set all three corresponding controls to null.
Precise numeric angle controls may also be used: left/right_arm/forearm/thigh/
shin_elevation 0..180 and _azimuth -180..180 (out=0, forward=90, across=150,
backward=-90). head/torso/root_pitch/yaw/roll, hand/foot_pitch/yaw/roll exist.
Prefer semantic directions to avoid confusing signs.

contact: auto (usual standing), both/left/right (fix named feet at original
positions), none (free legs or rotated body). Use none for sitting, kneeling,
lying/inversion; left or right for one-legged balance. null preserves contact
on edits. Leave timing and other parts unchanged unless requested. Current
pose controls and description are provided for interpreting corrections.
The engine can approximate body poses and transitions, including asymmetric
and inverted poses. It cannot create facial expressions, precise fingers,
objects, physics simulation, or walking/dancing cycles. A static action POSE
is allowed, e.g. frozen running posture; a repeating action is not implemented.
"""


def canonical_controls(changes):
    result = {}
    def put(name, value):
        if name in result and result[name] != value:
            raise PlanError('The model gave contradictory controls for ' + name)
        result[name] = value
    limb_parts = {side + '_' + part for side in ('left', 'right')
                  for part in ('arm', 'forearm', 'thigh', 'shin')}
    for name, value in changes.items():
        aliases = {'body': 'root', 'waist': 'torso', 'chest': 'torso', 'neck': 'head'}
        for side in ('left', 'right'):
            aliases.update({side + '_leg': side + '_thigh',
                            side + '_upper_leg': side + '_thigh',
                            side + '_knee': side + '_thigh',
                            side + '_lower_leg': side + '_shin',
                            side + '_upper_arm': side + '_arm',
                            side + '_lower_arm': side + '_forearm'})
        name = aliases.get(name, name)
        if name in LIMITS:
            put(name, value)
            continue
        if name not in limb_parts | {'head', 'torso', 'root'} or not isinstance(value, str):
            raise PlanError('Invalid pose control: ' + str(name))
        parts = value.lower().split(',')
        if len(parts) > 3 or (name in limb_parts and len(parts) != 1):
            raise PlanError('Invalid anatomical direction.')
        for part in parts:
            direction, separator, amount = part.strip().partition(':')
            if name in limb_parts:
                defaults = {'down': (0, 0), 'up': (180, 0), 'out': (90, 0),
                            'forward': (90, 90), 'backward': (90, -90), 'across': (90, 150)}
                defaults['left'] = (90, 0 if name.startswith('left_') else 180)
                defaults['right'] = (90, 0 if name.startswith('right_') else 180)
                if direction not in defaults:
                    raise PlanError('Invalid limb direction: ' + direction)
                elevation, azimuth = defaults[direction]
                put(name + '_elevation', float(amount) if separator else elevation)
                put(name + '_azimuth', azimuth)
            else:
                controls = {'forward': ('pitch', 1), 'backward': ('pitch', -1),
                            'left': ('yaw', 1), 'right': ('yaw', -1),
                            'tilt_left': ('roll', -1), 'tilt_right': ('roll', 1)}
                if direction not in controls:
                    raise PlanError('Invalid body direction: ' + direction)
                axis, sign = controls[direction]
                angle = float(amount) if separator else 30
                if angle < 0:
                    raise PlanError('Use the opposite direction with a positive angle.')
                put(name + '_' + axis, sign * angle)
    return result


def decode_pose_response(raw, current):
    def pairs(items):
        data = {}
        for key, value in items:
            if key in data:
                raise ValueError('Duplicate key')
            data[key] = value
        return data
    try:
        data = json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if not isinstance(data, dict) or set(data) != {'kind', 'changes', 'contact', 'message'}:
            raise ValueError('Invalid fields')
        kind, changes, contact, message = (data[key] for key in ('kind', 'changes', 'contact', 'message'))
        if not isinstance(message, str) or not 1 <= len(message) <= 180 or not isinstance(changes, dict):
            raise ValueError('Invalid values')
        if contact is not None and contact not in ('auto', 'both', 'left', 'right', 'none'):
            raise ValueError('Invalid contact setting')
        if kind in ('clarify', 'unsupported'):
            if changes or contact is not None:
                raise ValueError('Rejected request included changes')
            raise PlanError(message)
        if kind not in ('pose', 'edit') or (kind == 'edit' and current is None):
            raise ValueError('Invalid operation')
        if not changes and kind == 'edit' and contact is None:
            raise PlanError('Describe which part of the pose to change.')
        result = update_pose(current, canonical_controls(changes), contact, new_pose=kind == 'pose',
                             description=message if kind == 'pose' else None)
        return result, message
    except (TypeError, KeyError, ValueError) as exc:
        if isinstance(exc, PlanError):
            raise
        raise PlanError('The local model returned an invalid pose plan. No changes were applied.') from exc


def interpret_pose(text, current=None, model=None):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise PlanError('Enter a pose description of 1–2000 characters.')
    if text.strip().lower().rstrip('.!') in ('neutral', 'neutral pose', 'reset pose', 'stand normally'):
        return update_pose(current, {}, new_pose=True, description='Neutral standing pose'), 'Neutral standing pose'
    payload = {'current_pose': serialize_pose(current), 'request': text}
    raw = (model or get_model()).complete([
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': '{"current_pose":null,"request":"Put both hands on your hips."}'},
        {'role': 'assistant', 'content': json.dumps({
            'kind': 'pose', 'changes': {'left_hand_target_side': -.12,
                'left_hand_target_forward': .03, 'left_hand_target_height': .02,
                'right_hand_target_side': .12, 'right_hand_target_forward': .03,
                'right_hand_target_height': .02}, 'contact': 'auto', 'message': 'Hands on hips.'})},
        {'role': 'user', 'content': '{"current_pose":null,"request":"Sit with bent knees."}'},
        {'role': 'assistant', 'content': json.dumps({
            'kind': 'pose', 'changes': {'pelvis_drop': .25,
                'left_thigh': 'forward', 'right_thigh': 'forward',
                'left_shin': 'down', 'right_shin': 'down',
                'left_arm': 'down', 'right_arm': 'down'},
            'contact': 'none', 'message': 'Seated, knees bent.'})},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ], SCHEMA)
    plan, message = decode_pose_response(raw, current)
    return constrain_pose(plan, text, current, message)


def constrain_pose(plan, text, current=None, message='Requested pose'):
    """Shared checks for static posing, regardless of the planner entry point."""
    # Canonical anatomical constraints can be checked independently of AI prose.
    # This is an arm-direction constraint, not a catalog of named poses.
    relaxed = []
    lowered = text.lower()
    if re.search(r'\b(?:arms (?:relaxed|hanging|at (?:the |your )?sides)|relaxed arms)\b', lowered):
        relaxed = ['left', 'right']
    else:
        for side in ('left', 'right'):
            if re.search(r'\b' + side + r' arm (?:relaxed|hanging|at (?:the |your )?side)\b', lowered):
                relaxed.append(side)
    if relaxed:
        plan = PosePlan(values=tuple(sorted({**dict(plan.values), **{
            side + '_' + part + '_' + axis: 0
            for side in relaxed for part in ('arm', 'forearm')
            for axis in ('elevation', 'azimuth')}}.items())),
            contact=plan.contact, revision=plan.revision, description=plan.description)
    # "Stand" is an explicit gravity/support constraint, not a named pose preset.
    standing = re.search(r'\bstand(?:ing)?\b', lowered)
    inverted_support = re.search(r'\bstand(?:ing)?\s+on\s+(?:your\s+)?(?:hands?|head)\b', lowered)
    if standing and not inverted_support and not re.search(r'\bhandstand\b', lowered):
        values = dict(plan.values)
        values.update(root_pitch=0, root_roll=0)
        if values.get('pelvis_drop', 0) < 0:
            values['pelvis_drop'] = 0
        # A planted support leg is solved by contact IK, not free limb directions.
        for side in ('left', 'right'):
            if plan.contact in (side, 'both'):
                for name in list(values):
                    if name.startswith((side + '_thigh_', side + '_shin_')):
                        values.pop(name)
        plan = PosePlan(tuple(sorted(values.items())), plan.contact, plan.revision, plan.description)
    # The app's display summarizes the checked data, rather than trusting prose.
    before = dict(current.values) if current else {}
    changed = [f'{name.replace("_", " ")} {value:g}' for name, value in plan.values
               if before.get(name, 0) != value]
    changed.extend(f'{name.replace("_", " ")} reset' for name in before
                   if name not in dict(plan.values))
    summary = 'Local AI: ' + ('; '.join(changed) or message)
    return plan, summary
