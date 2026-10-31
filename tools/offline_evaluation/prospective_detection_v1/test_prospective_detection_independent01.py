"""Independent semantic-corruption fixtures; no actual recordings or inference."""
from __future__ import annotations

import copy
import unittest

import prospective_detection_dataset as dataset
import test_prospective_detection as fixture


class IndependentGeometrySemantics(unittest.TestCase):
    def setUp(self):
        self.case = fixture.BindingAndReview(methodName="test_valid_negative_frame_verify_and_failed_trial_preserved")
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.source = self.case.source()
        baseline = self.case.folder / "independent_valid_baseline.json"
        dataset.write_new(baseline, self.source)
        dataset.verify_recording(baseline, self.case.protocol_pin)

    def assert_mutation_refused(self, name, mutate):
        source = copy.deepcopy(self.source)
        mutate(source)
        path = self.case.folder / (name + ".json")
        dataset.write_new(path, source)
        with self.assertRaises(ValueError):
            dataset.verify_recording(path, self.case.protocol_pin)

    def test_in_view_actor_without_its_gt_cannot_become_negative_frame(self):
        self.assertEqual(self.source["frames"][0]["gt"], [])
        self.assert_mutation_refused("missing_inview_gt", lambda source:
            source["frames"][0]["actor_geometry"][0].update(status="KNOWN_IN_VIEW"))

    def test_unrecognized_known_status_is_not_a_visibility_certificate(self):
        self.assert_mutation_refused("invented_known_status", lambda source:
            source["frames"][0]["actor_geometry"][0].update(status="KNOWN_FAKE_CERTIFICATE"))

    def test_original_failed_terminal_cannot_be_relabelled_pass(self):
        self.assertEqual(self.source["terminal"]["status"], "FAIL")
        self.assert_mutation_refused("forged_pass", lambda source:
            source["terminal"].update(status="PASS"))

    def test_exact_source_proof_must_belong_to_selected_rgb(self):
        self.assert_mutation_refused("wrong_source_time", lambda source:
            source["frames"][0]["source_time_audit"].update(
                source_image_s=source["frames"][0]["source_time_s"] + 1.))

    def test_derived_coverage_cannot_claim_unobserved_images(self):
        self.assert_mutation_refused("forged_coverage", lambda source:
            source["coverage"].update(present_images=999))


if __name__ == "__main__":
    unittest.main(verbosity=2)
