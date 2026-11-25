from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from avatar_app.movement_library import contracts
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.motion import Surface
from avatar_app.planning.retrieval import MovementIndex, summarize_recipe


class MovementIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / "fixtures/ankles_feet_toes/v1/demo/profile.json"
        profile = contracts.loads(contracts.AvatarProfile, path.read_text(encoding="utf-8"))
        cls.catalog = catalog_for_profile(profile)
        cls.index = MovementIndex(cls.catalog)

    def test_paraphrases_rank_catalog_movements_first(self):
        for prompt, expected in (("Bend both knees", "knee.flex"),
                                 ("Make circles with your wrists", "wrist.circle")):
            with self.subTest(prompt=prompt):
                matches = self.index.search(prompt)
                self.assertEqual(matches.prompt, prompt)
                self.assertEqual(matches.candidates[0].id, expected)
                self.assertLessEqual(len(matches.candidates), 12)

    def test_unknown_metaphor_is_a_miss(self):
        matches = self.index.search("Be yesterday's unanswered question")
        self.assertTrue(matches.missed)
        self.assertIn("knee", dict(matches.family_counts))
        alternatives = self.index.family_alternatives("knee")
        self.assertIn("knee.flex", [candidate.id for candidate in alternatives])

    def test_expanded_catalog_is_bounded_and_order_independent(self):
        base = self.catalog.definitions["knee.flex"]
        entries = [replace(base, id=f"knee.flex_{i}") for i in range(200)]
        def build(rows):
            return MovementIndex(SimpleNamespace(definitions={row.id: row for row in rows}))
        first = build(entries)
        matches = first.search("bend my knees")
        self.assertEqual(matches, build(reversed(entries)).search("bend my knees"))
        self.assertEqual(len(matches.candidates), 12)
        self.assertEqual(len(first.family_alternatives("knee")), 12)
        self.assertLess(len(json.dumps(asdict(matches))), 22000)


def saved_case(group, rig, movement):
    folder = Path(__file__).parent / "fixtures" / group / "v1" / rig
    def read(kind, name):
        return contracts.loads(kind, (folder / name).read_text(encoding="utf-8"))
    profile = read(contracts.AvatarProfile, "profile.json")
    entry = read(contracts.MotionStateSnapshot, movement + "-entry.json")
    reviews = json.loads((folder / "reviews.json").read_text(encoding="utf-8"))
    return profile, entry, catalog_for_profile(profile), [
        contracts.from_dict(contracts.VerificationRecord, row) for row in reviews]


class EligibilityTests(unittest.TestCase):
    def test_review_requires_profile_evidence_and_effective_parameters(self):
        profile, entry, catalog, reviews = saved_case("hips_knees", "demo", "knee.flex")
        index = MovementIndex(catalog)
        def status(angle):
            result = index.retrieve("bend my knee", profile=profile, entry=entry,
                                    surfaces=(Surface(),), parameters={"knee.flex": {"angle": angle}})
            return {row.id: row.status for row in result.candidates}["knee.flex"]
        self.assertEqual(status(60), "experimental")
        review = next(row for row in reviews if row.definition_id == "knee.flex")
        # A narrower hypothetical review boundary within the real movement limits.
        specs = tuple(replace(spec, maximum=70) if spec.name == "angle" else spec
                      for spec in review.parameter_envelope)
        catalog.register_review(replace(review, parameter_envelope=specs), profile)
        self.assertEqual(status(70), "reviewed_for_envelope")
        self.assertEqual(status(71), "experimental")

    def test_missing_opposite_support_blocks_even_reviewed_knee(self):
        profile, entry, catalog, reviews = saved_case("hips_knees", "mixamo", "knee.flex")
        catalog.register_review(next(row for row in reviews if row.definition_id == "knee.flex"), profile)
        result = MovementIndex(catalog).retrieve("bend my knee", profile=profile,
            entry=replace(entry, active_contacts=()), surfaces=(Surface(),))
        self.assertNotIn("knee.flex", [row.id for row in result.candidates])
        self.assertIn(("knee.flex", "ENTRY_MISMATCH"), [(row.id, row.code) for row in result.limitations])

    def test_side_specific_palm_measurement_and_forearm_alternative(self):
        profile, entry, catalog, reviews = saved_case("elbows_wrists_hands", "mixamo", "hand.orient")
        catalog.register_review(next(row for row in reviews if row.definition_id == "hand.orient"), profile)
        index = MovementIndex(catalog)
        reduced = replace(entry, measured_controls=tuple(v for v in entry.measured_controls
                          if v.control_id != "left.hand.orientation"))
        prompt = "Palm facing up, twist the forearm"
        def retrieve(side):
            return index.retrieve(prompt, profile=profile, entry=reduced, surfaces=(Surface(),),
                                  parameters={"hand.orient": {"side": side}})
        left = retrieve("left")
        self.assertIn("forearm.twist", [row.id for row in left.candidates])
        self.assertIn(("hand.orient", "left.hand.orientation"),
                      [(row.id, row.control_id) for row in left.limitations])
        right = retrieve("right")
        self.assertIn(("hand.orient", "reviewed_for_envelope"), [(row.id, row.status) for row in right.candidates])


class PlannerContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures = Path(__file__).parent / "fixtures"
        saved = json.loads((fixtures / "recipe_schedules/v1/demo-sequential.json").read_text())
        folder = fixtures / "coordinated_body_moves/v1" / saved["entry_case"]
        cls.profile = contracts.loads(contracts.AvatarProfile, (folder / "profile.json").read_text())
        cls.entry = contracts.loads(contracts.MotionStateSnapshot, (folder / "entry.json").read_text())
        cls.resolved = contracts.from_dict(contracts.ResolvedRecipe, saved["resolved"])
        cls.index = MovementIndex(catalog_for_profile(cls.profile))

    def retrieve(self, prompt, **kwargs):
        return self.index.retrieve(prompt, profile=self.profile, surfaces=(Surface(),),
                                   entry=kwargs.pop("entry", self.entry), **kwargs)

    def test_compound_prompt_preserves_gesture_gait_and_support(self):
        prompt = "Walk while waving hello"
        limited = self.retrieve(prompt)
        self.assertIn("pattern.steps", [row.id for row in limited.limitations])
        folder = Path(__file__).parent / "fixtures/coordinated_body_moves/v1/demo/step-left"
        step = contracts.loads(contracts.MotionStateSnapshot, (folder / "entry.json").read_text())
        result = self.retrieve(prompt, entry=step)
        rows = {row.id: row for row in result.candidates}
        self.assertTrue({"arm.wave_gesture", "pattern.steps", "elbow.flex", "support.acquire_release"} <= rows.keys())
        self.assertEqual(dict(rows["support.acquire_release"].checked_parameters)["operation"], "release")

    def test_airborne_swimming_keeps_root_and_body_and_reports_blocked_travel(self):
        result = self.retrieve("Fly like the fish swims")
        self.assertTrue({"root.hover", "torso.wave", "support.acquire_release"} <= {c.id for c in result.candidates})
        self.assertIn("root.travel", [row.id for row in result.limitations])

    def test_missing_palm_and_fingers_preserve_greeting(self):
        # Model the anatomy limitations recorded for local Andrejs using a
        # calibrated fixture. This snapshot is not an Andrejs calibration.
        entry = replace(self.entry, measured_controls=tuple(v for v in self.entry.measured_controls
                        if not v.control_id.endswith(".hand.orientation") and "finger" not in v.control_id))
        result = self.retrieve("wave hello with palm facing up", entry=entry)
        self.assertIn("arm.wave_gesture", [row.id for row in result.candidates])
        self.assertIn("hand.orient", [row.id for row in result.limitations])
        self.assertTrue(self.retrieve("Yesterday's unanswered question", entry=entry).missed)

    def test_targeted_edit_preserves_authored_scope_and_timing(self):
        prompt = "Make just that gesture slower"
        result = self.retrieve(prompt, resolved=self.resolved, target_instance_id="gesture")
        data = json.loads(result.planner_context())
        self.assertEqual((data["prompt"], data["target_instance_id"]), (prompt, "gesture"))
        self.assertIn("arm.stroke", [row.id for row in (*result.candidates, *result.limitations)])
        recipe = data["recipe_context"]
        self.assertEqual([row["id"] for row in recipe["instances"]], ["seat", "gesture"])
        self.assertEqual(recipe["relations"], [contracts.to_dict(r) for r in self.resolved.recipe.relations])
        self.assertEqual(recipe["contacts"], [contracts.to_dict(r) for r in self.resolved.merged_contacts])
        self.assertEqual(recipe["goals"], [contracts.to_dict(r) for r in self.resolved.recipe.hard_goals])
        self.assertNotIn("tracks", recipe)
        with self.assertRaises(contracts.MotionContractError):
            result.planner_context(character_budget=100)
        with self.assertRaises(contracts.MotionContractError):
            self.retrieve(prompt, resolved=self.resolved, target_instance_id="missing")

    def test_filtered_family_expansion_and_prompt_side(self):
        miss = self.retrieve("Yesterday glimmers")
        expanded = self.retrieve(miss.prompt, family="wrist")
        self.assertTrue(miss.missed)
        self.assertEqual(expanded.expanded_family, "wrist")
        self.assertTrue(expanded.missed)
        self.assertEqual(expanded.candidates, ())
        self.assertTrue(expanded.alternatives)
        self.assertTrue(json.loads(expanded.planner_context())["missed"])
        self.assertTrue(all(row.id.startswith("wrist.") and row.status != "unchecked"
                            for row in expanded.alternatives))
        right = self.retrieve("Wave with your right hand")
        wave = next(row for row in right.candidates if row.id == "arm.wave_gesture")
        self.assertEqual(dict(wave.checked_parameters)["side"], "right")

    def test_blocked_edit_does_not_substitute_a_different_movement(self):
        result = self.retrieve("Make the gesture more like a wave", resolved=self.resolved,
                               target_instance_id="gesture", parameters={"arm.stroke": {"unknown": 1}})
        self.assertTrue(result.missed)
        self.assertEqual([row.id for row in result.limitations], ["arm.stroke"])
        self.assertEqual(result.target_instance_id, "gesture")

    def test_summary_preserves_an_explicit_lock(self):
        path = Path(__file__).parent / "fixtures/movement_contracts/v1/valid/resolved-recipe.json"
        resolved = contracts.loads(contracts.ResolvedRecipe, path.read_text())
        summary = summarize_recipe(resolved)
        self.assertTrue(summary["goals"][0]["locked"])
        self.assertEqual(summary["goals"][0]["target"], contracts.to_dict(resolved.recipe.hard_goals[0].target))


def check_local_andrejs():
    """Native Blender smoke for the local Stage 08 missing-palm FBX."""
    from avatar_app.blender.avatar import import_avatar
    from avatar_app.blender.rig_profile import calibrate_joint_frames, capture_motion_state
    path = Path(__file__).resolve().parents[1] / "Hip Hop Andrejs.fbx"
    handle = import_avatar(str(path))
    profile = calibrate_joint_frames(handle, recorded_at="2026-11-25", include_head_aim=True)
    entry = capture_motion_state(handle, profile, revision=0)
    index = MovementIndex(catalog_for_profile(profile))
    def query(prompt):
        return index.retrieve(prompt, profile=profile, entry=entry, surfaces=(Surface(),))
    assert query("Nod your head").candidates[0].id == "head.nod"
    palm = query("Turn the left palm upward")
    assert palm.missed and any(row.control_id == "reference.left.palm" for row in palm.limitations)
    assert query("Yesterday glimmers").missed


def check_trial_avatar(path):
    """Re-import the exported trial FBX and exercise retrieval without demo metadata."""
    from avatar_app.blender.avatar import import_avatar
    from avatar_app.blender.rig_profile import calibrate_joint_frames, capture_motion_state
    from avatar_app.movement_library.composer import compose_recipe
    handle = import_avatar(str(path))
    profile = calibrate_joint_frames(handle, recorded_at="2026-11-25", include_head_aim=True)
    entry = capture_motion_state(handle, profile, revision=0)
    catalog = catalog_for_profile(profile)
    index = MovementIndex(catalog)
    def query(prompt, **kwargs):
        return index.retrieve(prompt, profile=profile, entry=entry, surfaces=(Surface(),), **kwargs)
    assert query("Nod your head").candidates[0].id == "head.nod"
    palm = query("Turn the left palm upward")
    assert palm.missed and any(row.control_id == "reference.left.palm" for row in palm.limitations)
    miss = query("Yesterday glimmers")
    assert miss.prompt == "Yesterday glimmers" and miss.missed
    widened = query(miss.prompt, family="head")
    assert widened.missed and any(row.id == "head.nod" for row in widened.alternatives)
    instance = contracts.MovementInstance("first_nod", "head.nod", 1, (), ("request",))
    coverage = contracts.ClauseCoverage("request", "Nod your head", "fulfilled", ("first_nod",))
    recipe = contracts.MotionRecipe("trial.nod", profile.avatar_id, profile.version, entry.revision,
                                    "new", (instance,), (), (), (), None, (coverage,))
    resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
    edit = "Take longer on just that nod"
    result = query(edit, resolved=resolved, target_instance_id="first_nod",
                   parameters={"head.nod": {"duration_s": 2.0}})
    assert result.prompt == edit and result.target_instance_id == "first_nod"
    assert result.recipe_context["recipe_id"] == "trial.nod"
    assert result.candidates[0].id == "head.nod"
    assert dict(result.candidates[0].checked_parameters)["duration_s"] == 2.0
    return profile.avatar_id, len(handle.rig.data.bones), sum(o.type == "MESH" for o in handle.objects)
