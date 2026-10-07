from dataclasses import dataclass


class PlanError(ValueError):
    """A request cannot be represented by the available motion controls."""


@dataclass(frozen=True)
class MotionPlan:
    action: str = 'trex_transition'
    duration: float = 2.0
    fps: int = 30
    crouch: float = 0.08  # pelvis drop as a fraction of standing height
    arm_lift: float = 0.0
    revision: int = 0


@dataclass(frozen=True)
class PlanPatch:
    base_revision: int
    changes: tuple[tuple[str, float], ...]
