"""Small supplement fixtures; no colcon, ROS, simulation or real source copy."""
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import development_freeze_build as build


class BuildSupplementTests(unittest.TestCase):
    def review(self):
        return {'development_resource_override': build.expected_override(),
                'toolchain_canonical_sha256': build.GENERIC_CANONICAL,
                'files': {build.RECEIPT['path']: build.RECEIPT['sha256'],
                          'planning/reliability-v4-preregistration.json': '1'*64}}

    def test_real_manifest_binds_reused_tools_and_separate_guard(self):
        manifest = build.tool_manifest()
        self.assertEqual(manifest['reused_generic_canonical_sha256'], build.GENERIC_CANONICAL)
        self.assertEqual(set(manifest['files']), set(build.OWN_FILES))
        self.assertIn('resource_guard', manifest)
        self.assertFalse(manifest['legacy_runtime_contracts_called'])
        self.assertFalse(manifest['dependency_globals_modified'])

    def test_exact_override_is_bound_with_actual_reviewed_receipt(self):
        review = self.review()
        actual = build.supplement_binding(review)
        self.assertEqual(actual['override'], review['development_resource_override'])
        self.assertEqual(actual['reviewed_protocol_sha256'], '1'*64)

    def test_missing_changed_or_loose_override_is_rejected(self):
        for defect in ('missing', 'pending', 'wrong_tools', 'wrong_receipt', '640',
                       'legacy_claim', 'readiness', 'numeric_bool', 'extra'):
            with self.subTest(defect=defect):
                review = self.review()
                override = review['development_resource_override']
                if defect == 'missing': review.pop('development_resource_override')
                elif defect == 'pending': override['status'] = 'PENDING'
                elif defect == 'wrong_tools': override['tools_canonical_sha256'] = '0'*64
                elif defect == 'wrong_receipt': override['receipt']['sha256'] = '0'*64
                elif defect == '640': override['resource_revision'] = 'car_train20_04_m640_cpu4_v1'
                elif defect == 'legacy_claim': override['legacy640_runtime_acceptance_claimed'] = True
                elif defect == 'readiness': override['runtime_acceptance_claimed'] = True
                elif defect == 'numeric_bool': override['supersedes_legacy_resource_choice_only'] = 1
                else: override['unreviewed'] = True
                with self.assertRaises(ValueError): build.supplement_binding(review)

    def test_old_base_or_unbound512_receipt_cannot_certify_new_driver(self):
        for defect in ('old_base', 'missing_receipt', 'changed_receipt', 'missing_protocol'):
            with self.subTest(defect=defect):
                review = self.review()
                if defect == 'old_base': review['toolchain_canonical_sha256'] = '0'*64
                elif defect == 'missing_receipt': review['files'].pop(build.RECEIPT['path'])
                elif defect == 'changed_receipt': review['files'][build.RECEIPT['path']] = '0'*64
                else: review['files'].pop('planning/reliability-v4-preregistration.json')
                with self.assertRaises(ValueError): build.supplement_binding(review)

    def test_review_load_adds_supplement_check_before_any_action(self):
        review = self.review()
        with patch.object(build.generic, 'load_review', return_value=review):
            self.assertIs(build.load_review('explicit.json', '1'*64, 'build'), review)
        review.pop('development_resource_override')
        with patch.object(build.generic, 'load_review', return_value=review), self.assertRaises(ValueError):
            build.load_review('legacy.json', '1'*64, 'build')

    def test_action_binding_preserves_all_originals_and_adds_new_identity(self):
        review = self.review()
        old = {'source': {'sha': '1'}, 'review': {'sha': '2'}, 'closed_original_evidence': {'sha': '3'}}
        with patch.object(build.generic, 'action_binding', return_value=old):
            actual = build.action_binding(review, 'build')
        self.assertEqual({key: actual[key] for key in old}, old)
        self.assertEqual(actual['development_resource_override'], build.supplement_binding(review))

    def test_runtime_explicitly_uses512_guard_and_never_old_resource_guard(self):
        review = self.review()
        expected = {'resource': {'inference_image_size': 512, 'inference_threads': 4,
            'registration': {'revision': build.resource.REVISION, 'receipt': dict(build.RECEIPT),
                             'scope': build.resource.SCOPE},
            'receipt': {'path': str(Path('/explicit')/build.RECEIPT['path']), 'sha256': build.RECEIPT['sha256']},
            'model_sha256': build.resource.MODEL_SHA, 'scope': build.resource.SCOPE,
            'closed_loop_validated': False, 'formal_seed_use_authorized': False,
            'evidence_bindings': [{'fixture': 'bounded mocked file reader only'}]}, 'safety': 'original contract'}
        with patch.object(build.generic, 'runtime_contracts', side_effect=AssertionError('legacy640 forbidden')), \
             patch.object(build.resource, 'verify_runtime_evidence', return_value=expected), \
             patch.object(build.resource, 'runtime_contracts', return_value=expected) as guard:
            self.assertEqual(build.runtime_contracts(review, '/explicit'), expected)
            guard.assert_called_once_with(review, '/explicit')
        for bad in ({}, {'resource': {'inference_image_size': 640}}):
            with patch.object(build.resource, 'runtime_contracts', return_value=bad), self.assertRaises(ValueError):
                build.runtime_contracts(review, '/explicit')

    def test_strict512_check_rejects_legacy_or_empty_postbuild_evidence(self):
        for runtime in ({}, {'resource': {}}, {'resource': {'inference_image_size': 640}},
                        {'resource': {'inference_image_size': 512}}):
            with self.subTest(runtime=runtime), \
                 patch.object(build.resource, 'verify_runtime_evidence', return_value=runtime), \
                 self.assertRaisesRegex(ValueError, 'complete512'):
                build.verify_512_runtime(runtime, '/explicit')

    def test_prepare_checks_resource_without_reserving_a_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = {**self.review(), 'source_root': tmp,
                      'frozen_root': tmp+'/new_source', 'results_root': tmp+'/new_results'}
            with patch.object(build, 'runtime_contracts', return_value={'fixture': True}), \
                 patch.object(build.resource, 'verify_runtime_evidence', return_value=True):
                actual = build.prepare(review)
                self.assertFalse(actual['root_created'])
                self.assertFalse(Path(review['frozen_root']).exists())
                Path(review['results_root']).mkdir()
                with self.assertRaises(ValueError): build.prepare(review)

    def test_copy_refuses_existing_roots_before_copy_or_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = {**self.review(), 'frozen_root': tmp, 'results_root': tmp+'/results'}
            with patch.object(build, 'runtime_contracts', side_effect=AssertionError('no runtime')), \
                 patch.object(build.generic, 'copy_registered_file', side_effect=AssertionError('no copy')), \
                 self.assertRaises(ValueError): build.copy_source(review)

    def test_missing_final_review_refuses_before_launcher(self):
        with patch.object(build, 'launch', side_effect=AssertionError('no action')):
            self.assertEqual(build.main(['build']), 2)

    def test_shell_preserves_clean_env_coldbuild_and_explicit_supplement_entry(self):
        text = (build.EXTERNAL/'development_freeze_build.sh').read_text(encoding='utf-8')
        self.assertNotIn('reviewed_freeze_build.py', text)
        self.assertIn('development_freeze_build.py', text)
        self.assertIn('DEVELOPMENT_FREEZE_PARENT_PID', text)
        self.assertIn('unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH', text)
        self.assertIn('--internal-phase post-build', text)
        self.assertIn('CMAKE_BUILD_PARALLEL_LEVEL=2', text)


if __name__ == '__main__':
    unittest.main()
