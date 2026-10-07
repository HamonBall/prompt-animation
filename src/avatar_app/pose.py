"""General skeletal pose contract, independent of pose names and Blender."""
from dataclasses import dataclass
import math
from .models import PlanError


LIMITS = {
    'duration': (0.5, 8),
    'grounding': (0, 1),
    'pelvis_drop': (-0.3, 0.65), 'pelvis_forward': (-0.75, 0.75),
    'pelvis_side': (-0.75, 0.75),
    'root_pitch': (-180, 180), 'root_yaw': (-180, 180), 'root_roll': (-180, 180),
    'torso_pitch': (-90, 150), 'torso_yaw': (-120, 120), 'torso_roll': (-90, 90),
    'head_pitch': (-90, 90), 'head_yaw': (-100, 100), 'head_roll': (-70, 70),
}
for side in ('left', 'right'):
    for part in ('arm', 'forearm', 'thigh', 'shin'):
        LIMITS[f'{side}_{part}_elevation'] = (0, 180)
        LIMITS[f'{side}_{part}_azimuth'] = (-180, 180)
    for part in ('hand', 'foot'):
        for axis in ('pitch', 'yaw', 'roll'):
            LIMITS[f'{side}_{part}_{axis}'] = (-90, 90)
    for axis in ('side', 'forward', 'height'):
        LIMITS[f'{side}_hand_target_{axis}'] = (-0.8, 0.8)


@dataclass(frozen=True)
class PosePlan:
    values: tuple[tuple[str, float], ...] = ()
    contact: str = 'auto'
    revision: int = 0
    description: str = 'Neutral standing pose'

    @property
    def duration(self):
        return self.get('duration', 2.0)

    @property
    def fps(self):
        return 30

    def get(self, name, default=0.0):
        return dict(self.values).get(name, default)


def validate_pose(plan):
    if plan.contact not in ('auto', 'both', 'left', 'right', 'none'):
        raise PlanError('Invalid foot-contact setting.')
    values = dict(plan.values)
    if len(values) != len(plan.values):
        raise PlanError('Duplicate pose control.')
    for name, value in plan.values:
        if name not in LIMITS or type(value) not in (float, int) or not math.isfinite(value):
            raise PlanError('Invalid pose control: ' + str(name))
        low, high = LIMITS[name]
        if not low <= value <= high:
            raise PlanError(f'{name} must be between {low:g} and {high:g}.')
        if name == 'grounding' and value not in (0, 1):
            raise PlanError('grounding must be 0 or 1.')
    for side in ('left', 'right'):
        targets = [side + '_hand_target_' + axis for axis in ('side', 'forward', 'height')]
        if any(name in values for name in targets) and not all(name in values for name in targets):
            raise PlanError(f'An explicit {side} hand target needs side, forward, and height.')
    return plan


def update_pose(current, changes, contact=None, new_pose=False, description=None):
    if not isinstance(changes, dict):
        raise PlanError('Pose changes must be an object.')
    values = {} if new_pose or current is None else dict(current.values)
    for name, value in changes.items():
        if name not in LIMITS:
            raise PlanError('Invalid pose control: ' + str(name))
        if value is None:
            values.pop(name, None)
        else:
            values[name] = value
    return validate_pose(PosePlan(
        values=tuple(sorted(values.items())),
        contact=contact or ('auto' if new_pose or current is None else current.contact),
        revision=current.revision + 1 if current else 0,
        description=description or (current.description if current else 'Requested pose')))


def serialize_pose(plan):
    if plan is None:
        return None
    return {'controls': dict(plan.values), 'contact': plan.contact,
            'revision': plan.revision, 'description': plan.description}
