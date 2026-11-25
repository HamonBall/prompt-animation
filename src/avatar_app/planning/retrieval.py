"""Deterministic metadata search for the movement planner."""
from collections import Counter
from dataclasses import asdict, dataclass, replace
import json
import re

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement
from avatar_app.movement_library.registry import validate_snapshot

MAX_CANDIDATES = 12
_WORDS = re.compile(r"[a-z0-9]+")
_COMMON = frozenset("a an and as at by for from in into is it left like me my of on or right the to with your".split())
_TERMS = {
    "knees": "knee", "wrists": "wrist", "hands": "hand",
    "bend": "flex", "bending": "flex", "flexion": "flex", "bent": "flex",
    "circles": "circle", "circling": "circle", "circular": "circle",
    "orientation": "orient", "facing": "orient", "palms": "hand", "palm": "hand",
}
# Descriptive terms for capabilities whose implementation names use different
# vocabulary. A prompt can match any combination of these and catalog fields.
_DESCRIPTORS = {
    "pattern.steps": "walk walking gait strides strolling",
    "body.step": "walk walking gait stride stepping",
    "arm.wave_gesture": "greet greeting waving hello goodbye",
    "arm.raise": "greet greeting waving",
    "root.hover": "fly flying airborne float floating aloft",
    "root.travel": "fly flying swim swimming swims glide gliding",
    "torso.wave": "undulate undulation swim swimming swims ripple",
    "hand.trace": "stroke swimming tracing",
    "forearm.twist": "palm rotate rotation",
}
_HELPERS = {
    "pattern.steps": ("body.step", "support.acquire_release"),
    "body.step": ("support.acquire_release",),
    "root.hover": ("root.travel", "support.acquire_release"),
    "arm.wave_gesture": ("arm.raise", "elbow.flex"),
}


def _terms(*fields):
    return frozenset(_TERMS.get(word, word) for field in fields
                     for word in _WORDS.findall(field.lower()) if word not in _COMMON)


@dataclass(frozen=True)
class Candidate:
    id: str
    version: int
    description: str
    status: str = "unchecked"
    checked_parameters: tuple = ()


@dataclass(frozen=True)
class Limitation:
    id: str
    code: str
    reason: str
    control_id: str | None = None


@dataclass(frozen=True)
class CatalogMatches:
    prompt: str
    candidates: tuple[Candidate, ...]
    family_counts: tuple[tuple[str, int], ...]
    limitations: tuple[Limitation, ...] = ()
    recipe_context: dict | None = None
    target_instance_id: str | None = None
    expanded_family: str | None = None
    alternatives: tuple[Candidate, ...] = ()

    @property
    def missed(self):
        return not self.candidates

    def planner_context(self, *, character_budget=22000):
        """Serialize retrieval's share of the caller's model-message budget."""
        payload = {**asdict(self), "missed": self.missed}
        if self.expanded_family is None:
            del payload["alternatives"]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded) > min(character_budget, 22000):
            c.fail("RESOURCE_LIMIT", "Retrieved context exceeds the remaining model-message budget")
        return encoded


def summarize_recipe(resolved):
    """Project authored targets and contact intervals without motion tracks."""
    recipe = resolved.recipe
    def instance_row(instance):
        return {
            "id": instance.instance_id, "movement": instance.definition_id,
            "version": instance.definition_version,
            "parameters": {p.name: p.value for p in instance.parameters},
            "explicit": (tuple(p.name for p in instance.parameters) if instance.explicit_parameters is None
                         else instance.explicit_parameters),
            "clauses": instance.clause_ids,
        }
    return {
        "recipe_id": recipe.recipe_id, "base_revision": recipe.base_revision,
        "avatar_id": recipe.avatar_id, "profile_version": recipe.profile_version,
        "instances": [instance_row(row) for row in recipe.instances],
        "transitions": [instance_row(row) for row in resolved.transitions],
        "schedule": [(row.instance_id, row.interval.start_s, row.interval.end_s)
                     for row in resolved.scheduled_instances],
        "relations": [c.to_dict(row) for row in recipe.relations],
        "goals": [c.to_dict(row) for row in recipe.hard_goals],
        "contacts": [c.to_dict(row) for row in resolved.merged_contacts],
        "loop": c.to_dict(recipe.loop) if recipe.loop else None,
        "styles": [c.to_dict(row) for row in recipe.optional_styles],
        "clauses": [c.to_dict(row) for row in recipe.clause_coverage],
    }


class MovementIndex:
    """Rank discovery candidates. Execution eligibility is checked separately."""

    def __init__(self, catalog):
        self._catalog = catalog
        self._rows = []
        families = Counter()
        for definition in catalog.definitions.values():
            families[definition.id.partition(".")[0]] += 1
            identity = _terms(definition.id, _DESCRIPTORS.get(definition.id, ""))
            metadata = _terms(definition.description, *definition.semantic_tags,
                              *definition.owned_chains, *definition.required_capabilities,
                              *(r.target.control_id for r in definition.entry_conditions),
                              *(r.anchor_id for r in definition.contact_requirements))
            candidate = Candidate(definition.id, definition.version, definition.description)
            self._rows.append((candidate, identity, metadata))
        self.family_counts = tuple(sorted(families.items()))

    def _rank(self, prompt):
        exact = self._catalog.definitions.get(prompt.strip().lower())
        if exact is not None:
            return [Candidate(exact.id, exact.version, exact.description)]
        query = _terms(prompt)
        matches = []
        for definition, identity, metadata in self._rows:
            score = 3 * len(query & identity) + len(query & metadata)
            if score:
                matches.append((-score, definition.id, definition))
        return [row[2] for row in sorted(matches)]

    def search(self, prompt):
        candidates = tuple(self._rank(prompt)[:MAX_CANDIDATES])
        return CatalogMatches(prompt, candidates, self.family_counts)

    def retrieve(self, prompt, *, profile, entry, surfaces, parameters=None, family=None,
                 resolved=None, target_instance_id=None):
        """Check a concrete entry and proposed per-definition values before truncation.

        A family lookup widens discovery explicitly. Its results are alternatives
        and the caller can retain the original search miss.
        """
        validate_snapshot(entry, profile)
        proposed = dict(parameters or {})
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 2000 or not prompt.strip():
            c.fail("INVALID_PARAMETER", "Enter a movement prompt of 1–2000 characters")
        if resolved and (resolved.recipe.avatar_id, resolved.recipe.profile_version) != (profile.avatar_id, profile.version):
            c.fail("ENTRY_MISMATCH", "Correction recipe belongs to a different avatar profile")
        if family is None:
            ranked = self._rank(prompt)
        else:
            ranked = sorted((row[0] for row in self._rows
                             if row[0].id.partition(".")[0] == family), key=lambda row: row.id)
        if target_instance_id is not None:
            instance = next((row for row in resolved.recipe.instances if row.instance_id == target_instance_id),
                            None) if resolved else None
            if instance is None:
                c.fail("UNKNOWN_ID", "Correction target is absent from the current recipe")
            definition = self._catalog.definitions.get(instance.definition_id)
            if definition is None or definition.version != instance.definition_version:
                c.fail("VERSION_MISMATCH", "Correction target requires its original movement definition")
            saved = {p.name: p.value for p in instance.parameters
                     if instance.explicit_parameters is None or p.name in instance.explicit_parameters}
            proposed[definition.id] = {**saved, **proposed.get(definition.id, {})}
            if family is None:
                ranked = [Candidate(definition.id, definition.version, definition.description)]
        candidates = []
        limitations = []
        words = set(_WORDS.findall(prompt.lower()))
        sides = words & {"left", "right", "both"}
        if words & {"palm", "palms"} and "hand.orient" not in self._catalog.definitions:
            hand_sides = sides & {"left", "right"} or {"left", "right"}
            for side in sorted(hand_sides):
                reference = f"reference.{side}.palm"
                if reference not in profile.capabilities:
                    limitations.append(Limitation("hand.orient", "MISSING_CAPABILITY",
                                                  "Rig lacks a calibrated palm reference", reference))
        pending = list(reversed(ranked))
        seen = set()
        primary_count = 0
        helper_ids = set()
        while pending and len(candidates) < MAX_CANDIDATES:
            candidate = pending.pop()
            if candidate.id in seen:
                continue
            seen.add(candidate.id)
            values = dict(proposed.get(candidate.id, {}))
            definition = self._catalog.definitions[candidate.id]
            if len(sides) == 1 and any(spec.name == "side" for spec in definition.parameter_specs):
                values.setdefault("side", next(iter(sides)))
            if candidate.id == "support.acquire_release" and candidate.id not in proposed and entry.active_contacts:
                values = {"operation": "release", "anchor": sorted(entry.active_contacts)[0]}
            try:
                checked = self._check(candidate, values, profile, entry, surfaces)
            except c.MotionContractError as exc:
                if len(limitations) < MAX_CANDIDATES:
                    limitations.append(Limitation(candidate.id, exc.code, str(exc), exc.control_id))
                continue
            candidates.append(checked)
            if family is None and candidate.id not in helper_ids and primary_count < 3:
                primary_count += 1
                for key in reversed(_HELPERS.get(candidate.id, ())):
                    helper = self._catalog.definitions.get(key)
                    if helper is not None and key not in seen:
                        helper_ids.add(key)
                        pending.append(Candidate(helper.id, helper.version, helper.description))
        checked = tuple(candidates)
        return CatalogMatches(prompt, checked if family is None else (), self.family_counts,
                              tuple(limitations), summarize_recipe(resolved) if resolved else None,
                              target_instance_id, family, checked if family is not None else ())

    def _check(self, candidate, parameters, profile, entry, surfaces):
        key = (candidate.id, candidate.version, profile.avatar_id, profile.version)
        review = self._catalog.reviews.get(key)
        if review and review.status == "unavailable_on_rig":
            c.fail("MISSING_CAPABILITY", "Review records this movement as unavailable on the rig")
        instance = instantiate_movement(candidate.id, parameters, instance_id="retrieval.probe",
                                        profile=profile, entry_state=entry, catalog=self._catalog)
        # Several registered moves declare conditional anatomy and contact
        # requirements inside the pure fragment builder, after resolving side.
        build_fragment(instance, entry, profile, surfaces, self._catalog)
        candidate = replace(candidate, checked_parameters=tuple((p.name, p.value) for p in instance.parameters
                            if p.name in instance.explicit_parameters or p.name in ("side", "lead", "anchor", "mode")))
        if review and review.status == "reviewed_for_envelope":
            envelope = {spec.name: spec for spec in review.parameter_envelope}
            try:
                for parameter in instance.parameters:
                    c.validate_parameter(envelope[parameter.name], parameter.value)
            except c.MotionContractError:
                return replace(candidate, status="experimental")
            return replace(candidate, status=review.status)
        return replace(candidate, status="experimental")

    def family_alternatives(self, family):
        """One bounded page for a chosen family, separate from prompt matches."""
        choices = (row[0] for row in self._rows if row[0].id.partition(".")[0] == family)
        return tuple(sorted(choices, key=lambda candidate: candidate.id)[:MAX_CANDIDATES])
