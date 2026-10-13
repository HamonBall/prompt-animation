"""Validated action timelines. Plain data; no Blender or model dependency."""
from dataclasses import dataclass, replace
import math
from .models import PlanError
from .pose import PosePlan, update_pose, validate_pose


BODY_PARTS = ('pelvis', 'root', 'torso', 'head', 'left_arm', 'right_arm',
              'left_forearm', 'right_forearm', 'left_thigh', 'right_thigh',
              'left_shin', 'right_shin', 'left_hand', 'right_hand', 'left_foot', 'right_foot')
CONTACT_PARTS = ('left_foot', 'right_foot', 'left_hand', 'right_hand', 'pelvis', 'back')


@dataclass(frozen=True)
class Surface:
    name: str = 'floor'
    height: float = 0.0  # metres in the preview scene
    center: tuple[float, float] | None = None  # world XY; a resolved seat
    size: tuple[float, float] | None = None


@dataclass(frozen=True)
class ContactConstraint:
    part: str
    surface: str = 'floor'
    start: float = 0.0  # fractions of this stage's duration
    end: float = 1.0
    position: tuple[float, float] | None = None  # side/forward, avatar-height units
    clearance: float = 0.0  # bone anchor above surface, avatar-height units
    acquire: float = .4  # seconds to acquire support
    release: float = .4  # seconds to release wrist support


@dataclass(frozen=True)
class MotionStage:
    id: str
    action: str
    body_parts: tuple[str, ...]
    targets: tuple[tuple[str, float | None], ...]
    duration: float = 1.0
    start: float | None = None  # None follows previous stage; explicit start allows overlap
    contacts: tuple[ContactConstraint, ...] = ()
    completion: tuple[str, ...] = ('targets',)


@dataclass(frozen=True)
class ActionPlan:
    stages: tuple[MotionStage, ...]
    initial: PosePlan = PosePlan()
    surfaces: tuple[Surface, ...] = (Surface(),)
    revision: int = 0
    description: str = 'Requested motion'
    resolved_final: PosePlan | None = None

    @property
    def fps(self):
        return 30

    @property
    def duration(self):
        return max(end for _, _, end in schedule(self))

    @property
    def final_pose(self):
        if self.resolved_final is not None:
            return self.resolved_final
        values = sample_controls(self, self.duration)
        feet = {c.part for s, start, _ in schedule(self) for c in s.contacts
                if start + c.start * s.duration <= self.duration <= start + c.end * s.duration}
        contact = ('both' if {'left_foot', 'right_foot'} <= feet else
                   'left' if 'left_foot' in feet else 'right' if 'right_foot' in feet else 'none')
        return update_pose(None, values, contact, description=self.description)


def affected_part(control):
    if control.startswith('pelvis_'):
        return 'pelvis'
    return next((part for part in sorted(BODY_PARTS, key=len, reverse=True)
                 if control.startswith(part + '_')), None)


def schedule(plan):
    result, cursor = [], 0.0
    for stage in plan.stages:
        start = cursor if stage.start is None else stage.start
        end = start + stage.duration
        result.append((stage, start, end))
        cursor = max(cursor, end)
    return result


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def validate_action(plan):
    if not isinstance(plan, ActionPlan) or not 1 <= len(plan.stages) <= 12:
        raise PlanError('An action needs 1–12 motion stages.')
    validate_pose(plan.initial)
    if plan.resolved_final is not None:
        validate_pose(plan.resolved_final)
    if type(plan.revision) is not int or plan.revision < 0:
        raise PlanError('Invalid action revision.')
    if not isinstance(plan.description, str) or not 1 <= len(plan.description) <= 180:
        raise PlanError('Invalid action description.')
    surfaces = {surface.name: surface for surface in plan.surfaces}
    if len(surfaces) != len(plan.surfaces) or 'floor' not in surfaces:
        raise PlanError('An action needs distinct surfaces including the floor.')
    if surfaces['floor'].height != 0:
        raise PlanError('The preview floor is at world height zero.')
    for surface in plan.surfaces:
        if not isinstance(surface.name, str) or not surface.name or not finite(surface.height) or not 0 <= surface.height <= 2:
            raise PlanError('Invalid resolved surface.')
        if (surface.center is None) != (surface.size is None):
            raise PlanError('A bounded surface needs its center and size.')
        if surface.center is not None and (len(surface.center) != 2 or len(surface.size) != 2 or
                any(not finite(v) or abs(v) > 20 for v in surface.center) or
                any(not finite(v) or not .1 <= v <= 10 for v in surface.size)):
            raise PlanError('Invalid surface bounds.')
    ids = set()
    current = plan.initial
    for stage in plan.stages:
        if not isinstance(stage.id, str) or not 1 <= len(stage.id) <= 48 or stage.id in ids:
            raise PlanError('Stage IDs must be distinct nonempty strings.')
        ids.add(stage.id)
        if not isinstance(stage.action, str) or not 1 <= len(stage.action) <= 100:
            raise PlanError('A stage needs an action description.')
        if not finite(stage.duration) or not .2 <= stage.duration <= 8:
            raise PlanError('Stage duration must be between 0.2 and 8 seconds.')
        if stage.start is not None and (not finite(stage.start) or not 0 <= stage.start <= 60):
            raise PlanError('Invalid stage start time.')
        if not stage.body_parts or any(part not in BODY_PARTS for part in stage.body_parts):
            raise PlanError('Invalid affected body parts.')
        targets = dict(stage.targets)
        if len(targets) != len(stage.targets) or not targets or 'duration' in targets:
            raise PlanError('Stage targets must be distinct body controls; use stage duration for timing.')
        if any(affected_part(key) not in stage.body_parts for key in targets if key != 'grounding'):
            raise PlanError('Stage targets must belong to the affected body parts.')
        current = update_pose(current, targets, 'none')
        if not stage.completion or any(item not in ('targets', 'contacts') for item in stage.completion):
            raise PlanError('Completion supports targets and contacts only.')
        if 'contacts' in stage.completion and not stage.contacts:
            raise PlanError('Contact completion needs contact constraints.')
        for contact in stage.contacts:
            if contact.part not in CONTACT_PARTS or contact.surface not in surfaces:
                raise PlanError('Contact needs a supported body part and a resolved surface.')
            if not finite(contact.start) or not finite(contact.end) or not 0 <= contact.start < contact.end <= 1:
                raise PlanError('Invalid contact activation interval.')
            if not finite(contact.clearance) or not 0 <= contact.clearance <= .2:
                raise PlanError('Invalid contact clearance.')
            if any(not finite(v) or not .05 <= v <= 8 for v in (contact.acquire, contact.release)):
                raise PlanError('Invalid contact acquisition/release timing.')
            if contact.position is not None and (len(contact.position) != 2 or any(
                    not finite(v) or abs(v) > 1 for v in contact.position)):
                raise PlanError('Invalid contact position.')
    intervals = schedule(plan)
    if max(end for _, _, end in intervals) > 60:
        raise PlanError('Motion must fit within 60 seconds.')
    for i, (first, start, end) in enumerate(intervals):
        for second, other_start, other_end in intervals[i + 1:]:
            if max(start, other_start) < min(end, other_end) - 1e-8:
                if set(dict(first.targets)) & set(dict(second.targets)):
                    raise PlanError('Overlapping stages cannot own the same body control.')
    # One body anchor may not attach to two surfaces simultaneously.
    contacts = [(c, start + c.start * s.duration, start + c.end * s.duration)
                for s, start, _ in intervals for c in s.contacts]
    for i, (a, start, end) in enumerate(contacts):
        for b, bs, be in contacts[i + 1:]:
            if a.part == b.part and max(start, bs) < min(end, be) - 1e-8:
                raise PlanError('Overlapping contacts cannot constrain the same body part.')
    return plan


def control_default(values, key):
    # A lower segment follows its upper segment when not explicitly specified.
    for lower, upper in (('forearm', 'arm'), ('shin', 'thigh')):
        if '_' + lower + '_' in key:
            return values.get(key.replace('_' + lower + '_', '_' + upper + '_'), 0.0)
    return 1.0 if key == 'grounding' else 0.0


def sample_controls(plan, time):
    """Blend each control from its value at stage start; unrelated stages may overlap."""
    values = dict(plan.initial.values)
    values.pop('duration', None)
    for stage, start, end in sorted(schedule(plan), key=lambda row: row[1]):
        if time < start:
            continue
        weight = min(1.0, max(0.0, (time - start) / stage.duration))
        weight = weight * weight * (3 - 2 * weight)
        for key, target in stage.targets:
            source = values.get(key, control_default(values, key))
            if target is None:
                if '_target_' in key or time >= end:
                    values.pop(key, None)
                continue
            if key == 'grounding':
                values[key] = 0 if target == 0 else (target if time >= end else source)
                continue
            # Coordinate targets are interpolated in their declared support frame.
            values[key] = blend_control(plan, stage, key, source, time)
    return values


def blend_control(plan, stage, key, source, time):
    """Monotone cubic Hermite curves carry velocity through adjacent targets."""
    rows = [(s, start, end, dict(s.targets)[key]) for s, start, end in schedule(plan)
            if key in dict(s.targets) and dict(s.targets)[key] is not None]
    rows.sort(key=lambda row: row[1])
    index = next(i for i, row in enumerate(rows) if row[0].id == stage.id)
    _, start, end, target = rows[index]
    t = min(1.0, max(0.0, (time - start) / stage.duration))
    slope = (target - source) / stage.duration
    def tangent(a, b):
        # Harmonic mean prevents overshoot and stops at direction reversals.
        return 2 * a * b / (a + b) if a * b > 0 else 0.0
    begin_speed, end_speed = 0.0, 0.0
    if index and abs(rows[index - 1][2] - start) < 1e-6:
        previous, _, _, previous_target = rows[index - 1]
        earlier = rows[index - 2][3] if index > 1 else plan.initial.get(key, control_default(dict(plan.initial.values), key))
        begin_speed = tangent((previous_target - earlier) / previous.duration, slope)
    if index + 1 < len(rows) and abs(rows[index + 1][1] - end) < 1e-6:
        following, _, _, following_target = rows[index + 1]
        end_speed = tangent(slope, (following_target - target) / following.duration)
    return ((2*t**3 - 3*t*t + 1) * source + (t**3 - 2*t*t + t) * stage.duration * begin_speed
            + (-2*t**3 + 3*t*t) * target + (t**3 - t*t) * stage.duration * end_speed)


def scale_timing(plan, factor):
    if not finite(factor) or not .1 <= factor <= 10:
        raise PlanError('Invalid timing multiplier.')
    return validate_action(replace(plan, revision=plan.revision + 1, resolved_final=None, stages=tuple(
        replace(s, duration=s.duration * factor,
                start=None if s.start is None else s.start * factor,
                contacts=tuple(replace(c, acquire=max(.05, c.acquire*factor),
                                       release=max(.05, c.release*factor)) for c in s.contacts))
        for s in plan.stages)))


def patch_stages(plan, patches):
    """Patch by stable ID, preserving every unrelated target, contact, and timing."""
    if not isinstance(patches, list) or not patches:
        raise PlanError('Provide stage patches.')
    stages = {s.id: s for s in plan.stages}
    seen = set()
    for patch in patches:
        if not isinstance(patch, dict) or not set(patch) <= {'id', 'targets', 'duration', 'start', 'contacts', 'action', 'completion'}:
            raise PlanError('Invalid stage patch.')
        key = patch.get('id')
        if key not in stages or key in seen:
            raise PlanError('Patch needs a distinct existing stage ID.')
        seen.add(key)
        stage = stages[key]
        changes = {k: v for k, v in patch.items() if k != 'id'}
        if 'targets' in changes:
            targets = dict(stage.targets)
            targets.update(changes['targets'])
            changes['targets'] = tuple(sorted(targets.items()))
            changes['body_parts'] = tuple(sorted(set(stage.body_parts) | {
                affected_part(k) for k in targets if affected_part(k)}))
        stages[key] = replace(stage, **changes)
    return validate_action(replace(plan, revision=plan.revision + 1, resolved_final=None,
                                   stages=tuple(stages[s.id] for s in plan.stages)))


def serialize_action(plan):
    from dataclasses import asdict
    return asdict(plan)


def action_from_pose(pose):
    targets = tuple((k, v) for k, v in pose.values if k != 'duration') or (('torso_pitch', 0),)
    parts = tuple(sorted({affected_part(k) for k, _ in targets if affected_part(k)})) or ('torso',)
    feet = {'both': ('left', 'right'), 'left': ('left',), 'right': ('right',), 'none': ()}
    sides = feet.get(pose.contact)
    if sides is None:
        sides = () if any(pose.get('root_' + a) for a in ('pitch', 'yaw', 'roll')) else tuple(
            side for side in ('left', 'right') if not any(k.startswith((side + '_thigh_', side + '_shin_',
                                                                      side + '_foot_target_'))
                                                       for k, _ in targets))
    return validate_action(ActionPlan((MotionStage('pose', 'Reach requested posture', parts, targets,
                                                   pose.duration, contacts=tuple(
                                                       ContactConstraint(side + '_foot') for side in sides)),),
                                      revision=pose.revision, description=pose.description))
