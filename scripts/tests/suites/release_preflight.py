#!/usr/bin/env python3

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/release'))
import preflight as gate

SOURCE = 'a' * 40
MAIN = 'b' * 40
ENVIRONMENT = {
    'id': 1, 'name': 'release',
    'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
    'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': True,
                          'reviewers': [{'type': 'User', 'reviewer': {'id': 2}}]}],
}
POLICIES = [{'total_count': 1, 'branch_policies': [{'id': 3, 'name': 'v*', 'type': 'tag'}]}]
BRANCH = {'name': 'main', 'protected': True, 'commit': {'sha': MAIN}}
RULES = [[{'type': 'pull_request', 'parameters': {'required_approving_review_count': 1,
           'dismiss_stale_reviews_on_push': True, 'require_last_push_approval': True}},
          {'type': 'required_status_checks', 'parameters': {'strict_required_status_checks_policy': True,
           'required_status_checks': [{'context': name, 'integration_id': 15368}
                                      for name in ('full-linux', 'full-macos', 'workflow-policy')]}}]]
IDENTITY = {
    'GITHUB_REPOSITORY': 'ddv1982/tailmux', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF_TYPE': 'tag',
    'GITHUB_REF': 'refs/tags/v1.2.3', 'GITHUB_REF_NAME': 'v1.2.3', 'GITHUB_SHA': SOURCE,
    'GITHUB_WORKFLOW_SHA': SOURCE,
    'GITHUB_WORKFLOW_REF': 'ddv1982/tailmux/.github/workflows/release.yml@refs/tags/v1.2.3',
    'RUNNER_ENVIRONMENT': 'github-hosted',
}


class ProtectionTests(unittest.TestCase):
    def test_protected_environment_and_main_accepted(self):
        gate.validate_environment(ENVIRONMENT, POLICIES, 'release')
        self.assertEqual(gate.validate_main(BRANCH, RULES), MAIN)
        other = {**ENVIRONMENT, 'name': 'release-acceptance'}
        gate.validate_environment(other, POLICIES, 'release-acceptance')

    def test_environment_missing_fields_and_unsafe_rules_rejected(self):
        cases = [None, {}, {**ENVIRONMENT, 'name': 'wrong'}, {**ENVIRONMENT, 'id': None}]
        for key in ENVIRONMENT:
            bad = copy.deepcopy(ENVIRONMENT)
            del bad[key]
            cases.append(bad)
        for field, value in (('prevent_self_review', False), ('reviewers', []),
                             ('reviewers', [{'type': 'User', 'reviewer': {}}])):
            bad = copy.deepcopy(ENVIRONMENT)
            bad['protection_rules'][0][field] = value
            cases.append(bad)
        for value in (None, {'protected_branches': True, 'custom_branch_policies': False},
                      {'protected_branches': False, 'custom_branch_policies': False}):
            cases.append({**ENVIRONMENT, 'deployment_branch_policy': value})
        for bad in cases:
            with self.subTest(environment=bad), self.assertRaises(ValueError):
                gate.validate_environment(bad, POLICIES, 'release')
        for policies in ([], [{}], [{'total_count': 0, 'branch_policies': []}],
                         [{'total_count': 1, 'branch_policies': [{'id': 3, 'name': '*', 'type': 'tag'}]}],
                         [{'total_count': 1, 'branch_policies': [{'id': 3, 'name': 'v*', 'type': 'branch'}]}],
                         POLICIES + POLICIES):
            with self.subTest(policies=policies), self.assertRaises(ValueError):
                gate.validate_environment(ENVIRONMENT, policies, 'release')

    def test_main_missing_active_review_or_required_checks_rejected(self):
        for branch in ({}, {**BRANCH, 'protected': False}, {**BRANCH, 'commit': {}}):
            with self.assertRaises(ValueError):
                gate.validate_main(branch, RULES)
        cases = [[], [[]], [[RULES[0][0]]], [[RULES[0][1]]]]
        wrong_app = copy.deepcopy(RULES)
        for status in wrong_app[0][1]['parameters']['required_status_checks']:
            status['integration_id'] = 1
        cases.append(wrong_app)
        for kind, key, value in ((0, 'required_approving_review_count', 0),
                                  (0, 'required_approving_review_count', True),
                                  (0, 'dismiss_stale_reviews_on_push', False),
                                  (0, 'require_last_push_approval', False),
                                  (1, 'strict_required_status_checks_policy', False),
                                  (1, 'required_status_checks', []),
                                  (1, 'required_status_checks', [{'context': 'full-linux', 'integration_id': None}])):
            bad = copy.deepcopy(RULES)
            bad[0][kind]['parameters'][key] = value
            cases.append(bad)
        for bad in cases:
            with self.subTest(rules=bad), self.assertRaises(ValueError):
                gate.validate_main(BRANCH, bad)

    def test_each_execution_identity_is_mandatory(self):
        request = gate.ReleaseRequest('v1.2.3', SOURCE)
        with patch.dict(os.environ, IDENTITY, clear=True), patch.object(gate, 'git', return_value=(SOURCE + '\n').encode()):
            gate.identity(request, ROOT)
            for key in IDENTITY:
                with self.subTest(key=key), patch.dict(os.environ, {key: 'wrong'}), self.assertRaises(ValueError):
                    gate.identity(request, ROOT)
        for values in ((b'b' * 40, b'a' * 40), (b'a' * 40, b'b' * 40)):
            with patch.dict(os.environ, IDENTITY, clear=True), patch.object(gate, 'git', side_effect=values), self.assertRaises(ValueError):
                gate.identity(request, ROOT)

    def test_api_failures_are_not_treated_as_empty_success(self):
        with patch.object(gate, 'run', side_effect=subprocess.CalledProcessError(1, ['gh', 'api'])):
            with self.assertRaises(subprocess.CalledProcessError):
                gate.api('environments/release')
        for raw in (b'{', b'{"id":1,"id":2}'):
            with patch.object(gate, 'run', return_value=raw), self.assertRaises(ValueError):
                gate.api('environments/release')

    def test_cli_fake_api_receipt_and_failure_do_not_write_success(self):
        with tempfile.TemporaryDirectory() as private:
            directory = Path(private)
            fixture = {
                'environments/release': ENVIRONMENT,
                'environments/release/deployment-branch-policies?per_page=100': POLICIES,
                'branches/main': BRANCH, 'rules/branches/main?per_page=100': RULES,
            }
            (directory / 'responses.json').write_text(json.dumps(fixture))
            (directory / 'gh').write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                "sys.exit(9) if os.environ.get('FAIL_API') else None\n"
                "endpoint=next(x for x in sys.argv if x.startswith('repos/')).split('/',3)[3]\n"
                "print(json.dumps(json.load(open(os.environ['FIXTURES']))[endpoint]))\n")
            (directory / 'git').write_text('#!/usr/bin/env python3\nimport os, sys\n'
                "sys.exit(int(os.environ.get('NOT_ANCESTOR', '0'))) if 'merge-base' in sys.argv else print('a'*40)\n")
            for name in ('gh', 'git'):
                (directory / name).chmod(0o700)
            env = {**os.environ, **IDENTITY, 'PATH': f'{directory}:{os.environ["PATH"]}',
                   'FIXTURES': str(directory / 'responses.json'), 'GITHUB_OUTPUT': str(directory / 'output')}
            command = [sys.executable, str(ROOT / 'scripts/release/preflight.py'), '--tag', 'v1.2.3',
                       '--source-sha', SOURCE, '--main-sha', MAIN]
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((directory / 'output').read_text(), f'main_sha={MAIN}\nsource_sha={SOURCE}\ntag=v1.2.3\n')
            for extra in ({'FAIL_API': '1'}, {'NOT_ANCESTOR': '1'}, {'GITHUB_WORKFLOW_SHA': 'c' * 40}):
                (directory / 'output').unlink(missing_ok=True)
                result = subprocess.run(command, env={**env, **extra}, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((directory / 'output').exists())
            (directory / 'output').unlink(missing_ok=True)
            result = subprocess.run(command[:-1] + ['c' * 40], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((directory / 'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
