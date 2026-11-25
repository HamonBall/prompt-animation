"""Bind validated foundation selections to a measured Blender entry."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from ..models import PlanError
from ..motion import ActionPlan, action_from_pose
from ..movement_library import contracts as c
from ..movement_library.compiler import compile_recipe
from ..movement_library.composer import compose_recipe
from ..movement_library.joints import catalog_for_profile
from ..movement_library.recipes import (
    compile_lie_sequence, compile_run_sequence, compile_walk_sequence, foundation_recipe,
)
from ..planning.presets import FoundationRequest, FoundationSelection
from ..pose import PosePlan
from .foot_mechanics import calibrate_feet
from .motion import build_action_frames
from .rig_profile import calibrate_joint_frames, capture_floor_entry
from .support_mechanics import calibrate_support


@dataclass(frozen=True)
class BoundFoundation:
    motion: c.ExecutableMotion
    profile: c.AvatarProfile
    continuations: tuple[Callable[[c.MotionStateSnapshot], c.ExecutableMotion], ...]
    endpoint_plan: ActionPlan | None = None


def prepare_preview_request(handle, candidate, current):
    """Bind reviewed public recipes from the app's initial standing result."""
    if not isinstance(candidate, FoundationRequest):
        return candidate, None
    name = candidate.selection.name
    if name not in ('wave', 'sit_seat') or not isinstance(current, PosePlan) or current.values:
        return candidate.plan, None
    if name == 'sit_seat' and not any(surface.name == 'seat' and .35 <= round(surface.height, 6) <= .55
                                      for surface in handle.surfaces):
        return candidate.plan, None
    revision = candidate.plan.revision
    try:
        profile = calibrate_feet(handle, calibrate_joint_frames(
            handle, recorded_at=date.today().isoformat(), include_head_aim=True))
        if name == 'sit_seat':
            profile = calibrate_support(handle, profile)
        bound = bind_foundation(handle, candidate.selection, profile, revision=revision)
        if name == 'sit_seat':
            bound = replace(bound, endpoint_plan=candidate.plan)
        return bound, revision
    except c.MotionContractError as exc:
        if exc.code not in ('MISSING_CAPABILITY', 'ENTRY_MISMATCH'):
            raise
        return candidate.plan, None


def bind_foundation(handle, selection, profile, *, revision, entry=None):
    """Compile on the Blender thread against current geometry and measured state."""
    if not isinstance(selection, FoundationSelection):
        raise PlanError('A recipe needs a validated foundation selection.')
    if entry is None:
        entry = capture_floor_entry(handle, profile, revision=revision)
    if entry.revision != revision:
        c.fail('STALE_REVISION', 'The measured entry belongs to a previous result')
    surfaces = tuple(handle.surfaces)
    options = dict(selection.options)
    if selection.tempo != 1. and selection.name != 'wave':
        c.fail('UNSUPPORTED_GOAL', 'This recipe has not been validated at a different speed')
    if selection.name in ('walk', 'run'):
        preset_height = (handle.rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
        if selection.name == 'walk':
            motion, following = compile_walk_sequence(entry, profile, surfaces, preset_height_m=preset_height,
                                                      arm_motion=True, **options)
        else:
            motion, following = compile_run_sequence(entry, profile, surfaces, preset_height_m=preset_height,
                                                     **options)
    elif selection.name == 'lie':
        motion, following = compile_lie_sequence(entry, profile, surfaces, floor_sit_arms=True)
    else:
        options.update(tempo=selection.tempo if selection.name == 'wave' else None,
                       compact_jump=selection.name == 'jump',
                       floor_sit_arms=selection.name == 'sit_floor',
                       chair_descent=selection.name == 'sit_seat')
        recipe = foundation_recipe(selection.name, entry, profile, **options)
        catalog = catalog_for_profile(profile)
        resolved = compose_recipe(recipe, entry, profile, surfaces, catalog)
        motion = compile_recipe(resolved, entry, profile, surfaces=surfaces, catalog=catalog)
        following = ()
    return BoundFoundation(motion, profile, following)


def request_frames(handle, candidate, progress=lambda fraction: None, *, approximate=False, revision=None):
    """Share the synchronous and modal bake entry for existing plans and bound recipes."""
    if isinstance(candidate, BoundFoundation):
        if revision != candidate.motion.entry_snapshot.revision:
            c.fail('STALE_REVISION', 'The bound recipe belongs to a previous result')
        if approximate:
            c.fail('UNSUPPORTED_GOAL', 'Bound recipes require strict motion review')
        return build_action_frames(handle, candidate.motion, progress, profile=candidate.profile,
                                   continuations=candidate.continuations, endpoint_plan=candidate.endpoint_plan)
    plan = candidate if isinstance(candidate, ActionPlan) else action_from_pose(candidate)
    return build_action_frames(handle, plan, progress, allow_experimental=approximate)


def bake_request(handle, candidate, progress=lambda fraction: None, *, approximate=False, revision=None):
    builder = request_frames(handle, candidate, progress, approximate=approximate, revision=revision)
    try:
        while True:
            next(builder)
    except StopIteration as completed:
        return completed.value
