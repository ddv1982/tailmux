#!/usr/bin/env python3
"""Fail closed on workflow syntax ambiguity and publisher policy drift."""

import argparse
from pathlib import Path
import re
import sys

import yaml
from yaml.events import AliasEvent

PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/attest": "1e69f48acb82d1966a394da916b4c1698aa569d6",
    "actions/upload-artifact": "cf430e030ddbb5b0abf93d22962f4752f3646cd9",
}
HOSTED = {"ubuntu-24.04", "macos-15"}
ACTIONLINT_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
PREFLIGHT = 'python3 scripts/release/preflight.py --tag "$TAG" --source-sha "$EXPECTED_SOURCE_SHA"'
RECHECK = ('test "$EXPECTED_SOURCE_SHA" = "$PREFLIGHT_SOURCE_SHA"\n' + PREFLIGHT
           + ' --main-sha "$REVIEWED_MAIN_SHA"')
ACCEPTANCE_GATE = ('python3 scripts/acceptance/release_gate.py --expected-sha "$EXPECTED_SOURCE_SHA" '
                   '--expected-merge-base "$EXPECTED_SOURCE_SHA"')
ACCEPTANCE_ENV = {key: '${{ vars.' + key + ' }}' for key in (
    "ACCEPTANCE_SOURCE_SHA", "ACCEPTANCE_ARTIFACT_ID", "ACCEPTANCE_ARCHIVE_SHA256", "ACCEPTANCE_REQUEST_SHA256")}

BUILD = ('mkdir -m 700 dist\npython3 scripts/release/package.py build --tag "$TAG" '
         '--source-sha "$EXPECTED_SOURCE_SHA" --output "dist/tailmux-${TAG}.tar.gz"')
PUBLISH = ('gh release create "$TAG" "dist/tailmux-${TAG}.tar.gz" --repo ddv1982/tailmux '
           '--verify-tag --target "$EXPECTED_SOURCE_SHA" --title "$TAG" --notes '
           '"Portable package. Verify publisher and expected source before unpacking. See docs/releases.md."')


class WorkflowLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        event = self.peek_event()
        if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
            raise ValueError("Workflow aliases and anchors are forbidden")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise ValueError("Workflow merges are forbidden")
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str or key in result:
                raise ValueError("Workflow keys must be unique strings")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


WorkflowLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in value if tag != "tag:yaml.org,2002:bool"]
    for key, value in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
WorkflowLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(text):
    document = yaml.load(text, Loader=WorkflowLoader)
    require(type(document) is dict, "Workflow must be a mapping")
    return document


def walk(value):
    if type(value) is dict:
        for key, child in value.items():
            require(key not in {"continue-on-error", "secrets", "container", "services"},
                    f"Forbidden workflow capability: {key}")
            walk(child)
    elif type(value) is list:
        for child in value:
            walk(child)


def common(document, acceptance=False):
    walk(document)
    require(document.get("permissions") == {}, "Workflow permissions must default to none")
    jobs = document.get("jobs")
    require(type(jobs) is dict and jobs, "Workflow jobs missing")
    for name, job in jobs.items():
        matrix = acceptance and name == "validate" and job.get("runs-on") == "${{ matrix.os }}" and job.get("strategy") == {
            "fail-fast": True, "matrix": {"os": ["ubuntu-24.04", "macos-15"]}}
        require(type(job) is dict and (job.get("runs-on") in HOSTED or matrix),
                f"{name} must use explicit hosted runners")
        require(type(job.get("timeout-minutes")) is int and 0 < job["timeout-minutes"] <= 30,
                f"{name} timeout missing")
        require("if" not in job and ("strategy" not in job or matrix), f"{name} may not bypass or vary required work")
        steps = job.get("steps")
        require(type(steps) is list and steps, f"{name} steps missing")
        for step in steps:
            require(type(step) is dict and "if" not in step, "Steps cannot skip required work")
            require(("uses" in step) != ("run" in step), "Each step must run or use one action")
            if "uses" in step:
                uses = step["uses"]
                require(type(uses) is str and uses.count("@") == 1, "Action must use reviewed SHA")
                action, sha = uses.split("@")
                require(PINS.get(action) == sha, f"Action pin needs independent review: {uses}")
                if action == "actions/checkout":
                    settings = step.get("with", {})
                    require(settings.get("persist-credentials") is False,
                            "Checkout must disable persisted credentials")
                    require(set(settings) <= {"persist-credentials", "fetch-depth"},
                            "Checkout cannot change publisher identity or token")


def validate_ci(document):
    common(document)
    require(document.get("on") == {"push": {"branches": ["**"]}, "pull_request": {"branches": ["**"]}},
            "CI must run only read-only push and pull_request events")
    require("env" not in document and "defaults" not in document, "CI cannot inject global commands or credentials")
    jobs = document["jobs"]
    require(set(jobs) == {"workflow-policy", "full-linux", "full-macos"}, "Required CI jobs changed")
    for name, job in jobs.items():
        require(job.get("permissions") == {"contents": "read"} and "environment" not in job,
                "Untrusted CI must have only contents read and no environment")
        require("needs" not in job and "env" not in job and "defaults" not in job, "CI jobs must run independently")
        for step in job["steps"]:
            require("env" not in step and "working-directory" not in step and "shell" not in step,
                    "CI steps cannot override checked execution context")
            if "uses" in step:
                require(step["uses"] == "actions/checkout@" + PINS["actions/checkout"], "CI uses checkout only")
        commands = '\n'.join(step.get("run", "") for step in job["steps"])
        require("secrets." not in commands and "github.token" not in commands, "CI cannot pass credentials to code")
        if name.startswith("full-"):
            require(any(step.get("run", "").strip() == ". .venv/bin/activate\nbash scripts/tests/run.sh full"
                        for step in job["steps"]),
                    "Complete platform suites must block CI")
            require(job["runs-on"] == ("macos-15" if name == "full-macos" else "ubuntu-24.04"),
                    "Both platform runners are required")
            require("jq shellcheck" in commands, "Platform tests require jq and shellcheck")
            require(".venv/bin/python -m pip install --require-hashes -r requirements-dev.txt" in commands,
                    "Platform tests require the reviewed development dependencies")
        else:
            install = job["steps"][1].get("run", "").strip().splitlines()
            require(len(install) == 6
                    and install[0] == "python3 -m venv .venv"
                    and install[1] == ".venv/bin/python -m pip install --require-hashes -r requirements-dev.txt"
                    and install[2] == "curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz --output /tmp/actionlint.tar.gz"
                    and install[3] == "echo '" + ACTIONLINT_SHA256 + "  /tmp/actionlint.tar.gz' | sha256sum --check --strict"
                    and install[4:] == ["mkdir /tmp/actionlint-bin", "tar -xzf /tmp/actionlint.tar.gz -C /tmp/actionlint-bin actionlint"],
                    "Development tools must retain pinned integrity checks before execution")
            validation = job["steps"][-1].get("run", "").strip().splitlines()
            require(validation == [".venv/bin/python scripts/release/check_workflows.py",
                                   "/tmp/actionlint-bin/actionlint -oneline .github/workflows/*.yml",
                                   ".venv/bin/python scripts/tests/suites/workflow_policy.py",
                                   "python3 scripts/tests/suites/release_cli.py",
                                   "python3 scripts/tests/suites/release_preflight.py"],
                    "Release policy checks must block on failure")



def validate_release(document):
    common(document)
    require(document.get("on") == {"push": {"tags": ["v*"]}}, "Release must originate at a version tag")
    require("env" not in document and "defaults" not in document, "Release cannot override global execution context")
    require(document.get("concurrency") == {"group": "release-${{ github.ref }}", "cancel-in-progress": False},
            "Release concurrency changed")
    jobs = document["jobs"]
    require(set(jobs) == {"preflight", "publish"}, "Release job boundary changed")
    preflight, publish = jobs["preflight"], jobs["publish"]
    require(preflight.get("permissions") == {"contents": "read", "actions": "read"}
            and "environment" not in preflight and "needs" not in preflight and "env" not in preflight,
            "Preflight must be unprivileged and precede any environment")
    require(preflight.get("outputs") == {
        key: '${{ steps.protection.outputs.' + key + ' }}' for key in ("main_sha", "source_sha", "tag")},
        "Preflight outputs must carry independently checked identities")
    require(publish.get("needs") == "preflight" and publish.get("environment") == "release",
            "Publisher requires successful preflight and release approval")
    require(publish.get("permissions") == {"contents": "write", "attestations": "write", "id-token": "write",
                                          "actions": "read"}, "Publisher permissions exceed reviewed scope")
    require(publish.get("env") == {
        "GH_TOKEN": "${{ github.token }}", "TAG": "${{ needs.preflight.outputs.tag }}",
        "EXPECTED_SOURCE_SHA": "${{ vars.RELEASE_SOURCE_SHA }}",
        "PREFLIGHT_SOURCE_SHA": "${{ needs.preflight.outputs.source_sha }}",
        "REVIEWED_MAIN_SHA": "${{ needs.preflight.outputs.main_sha }}"}, "Publisher expectations changed")
    for job in jobs.values():
        require(job["runs-on"] == "ubuntu-24.04" and "defaults" not in job, "Publisher must use reviewed hosted runner")
        for step in job["steps"]:
            require(set(step) <= {"name", "id", "uses", "with", "run", "env"}, "Unexpected publisher step capability")
        require(job["steps"][0].get("uses") == "actions/checkout@" + PINS["actions/checkout"]
                and job["steps"][0].get("with") == {"persist-credentials": False, "fetch-depth": 0},
                "Publisher requires exact tag checkout and full ancestry")
    before = preflight["steps"]
    require(len(before) == 2 and "env" not in before[0] and before[1].get("id") == "protection"
            and before[1].get("run", "").strip() == PREFLIGHT and before[1].get("env") == {
                "GH_TOKEN": "${{ github.token }}", "TAG": "${{ github.ref_name }}",
                "EXPECTED_SOURCE_SHA": "${{ vars.RELEASE_SOURCE_SHA }}"}, "Unprivileged preflight changed")
    steps = publish["steps"]
    require(len(steps) == 7, "Publisher step sequence changed")
    for index, command in ((1, RECHECK), (3, BUILD), (6, PUBLISH)):
        require(steps[index].get("run", "").strip() == command and "env" not in steps[index],
                "Required repeat-check, acceptance refusal, build, attest, publish order changed")
    require(steps[2].get("run", "").strip() == ACCEPTANCE_GATE and steps[2].get("env") == ACCEPTANCE_ENV,
            "Exact protected acceptance gate must precede build")
    archive = "dist/tailmux-${{ needs.preflight.outputs.tag }}.tar.gz"
    require(steps[4].get("uses") == "actions/attest@" + PINS["actions/attest"] and steps[4].get("with") == {
        "subject-path": archive, "push-to-registry": False, "create-storage-record": False},
        "Attestation must cover the exact final archive with standard provenance")
    require(steps[5].get("uses") == "actions/upload-artifact@" + PINS["actions/upload-artifact"]
            and steps[5].get("with") == {"name": "tailmux-${{ needs.preflight.outputs.tag }}", "path": archive,
                                        "if-no-files-found": "error", "retention-days": 7},
            "Upload must preserve the attested archive")
    require(all("env" not in steps[i] for i in (0, 4, 5)), "Action environment override forbidden")


def validate_acceptance(document):
    common(document, acceptance=True)
    require("env" not in document and "defaults" not in document, "Acceptance cannot override global context")
    event = document.get("on")
    require(type(event) is dict and set(event) == {"workflow_dispatch"}, "Acceptance requires manual dispatch")
    inputs = event["workflow_dispatch"].get("inputs", {})
    require(set(inputs) == {"expected_sha", "expected_merge_base", "evidence_artifact_id", "archive_sha256", "request_sha256"}
            and all(type(v) is dict and v.get("required") is True and v.get("type") == "string" for v in inputs.values()),
            "Acceptance expectations must be explicit")
    jobs = document["jobs"]
    require(set(jobs) == {"preflight", "validate"}, "Acceptance job boundary changed")
    preflight, validate = jobs["preflight"], jobs["validate"]
    for job in jobs.values():
        require(job.get("permissions") == {"contents": "read", "actions": "read"}
                and "env" not in job and "defaults" not in job, "Acceptance must remain read-only")
        require(job["steps"][0].get("uses") == "actions/checkout@" + PINS["actions/checkout"],
                "Acceptance must start with pinned event checkout")
        for step in job["steps"]:
            require("working-directory" not in step and "shell" not in step, "Acceptance context override forbidden")
            require("inputs." not in step.get("run", "") and "secrets." not in str(step),
                    "Acceptance inputs must enter through environment data, without secrets")
            if "uses" in step:
                require(step["uses"].split("@")[0] in {"actions/checkout", "actions/upload-artifact"},
                        "Acceptance cannot attest or publish")
    require(preflight.get("runs-on") == "ubuntu-24.04" and "environment" not in preflight
            and "needs" not in preflight and len(preflight["steps"]) == 3,
            "Acceptance preflight must precede environment execution")
    require(preflight["steps"][-1].get("run") ==
            'python3 scripts/acceptance/preflight.py --expected-sha "$EXPECTED_SHA"'
            and preflight["steps"][-1].get("env") == {
                "GH_TOKEN": "${{ github.token }}", "EXPECTED_SHA": "${{ inputs.expected_sha }}"},
            "Acceptance must check actual protection and source identity")
    require(validate.get("needs") == "preflight" and validate.get("environment") == "acceptance"
            and validate.get("strategy") == {"fail-fast": True, "matrix": {"os": ["ubuntu-24.04", "macos-15"]}}
            and validate.get("runs-on") == "${{ matrix.os }}" and len(validate["steps"]) == 4,
            "Both protected evidence-validation platforms are required")
    require(validate["steps"][1].get("run") == "python3 scripts/tests/suites/acceptance_cli.py",
            "Acceptance boundary tests must block")
    require(validate["steps"][2].get("run") ==
            'python3 scripts/acceptance/release_gate.py --expected-sha "$EXPECTED_SHA" --expected-merge-base "$EXPECTED_BASE" > acceptance-structure.json'
            and validate["steps"][2].get("env") == {
                "GH_TOKEN": "${{ github.token }}", "EXPECTED_SHA": "${{ inputs.expected_sha }}",
                "EXPECTED_BASE": "${{ inputs.expected_merge_base }}", "ACCEPTANCE_SOURCE_SHA": "${{ inputs.expected_sha }}",
                "ACCEPTANCE_ARTIFACT_ID": "${{ inputs.evidence_artifact_id }}",
                "ACCEPTANCE_ARCHIVE_SHA256": "${{ inputs.archive_sha256 }}",
                "ACCEPTANCE_REQUEST_SHA256": "${{ inputs.request_sha256 }}"},
            "Exact reviewed evidence gate and independent expectations are required")
    upload = validate["steps"][3]
    require(upload.get("uses") == "actions/upload-artifact@" + PINS["actions/upload-artifact"]
            and upload.get("with", {}).get("path") == "acceptance-structure.json"
            and upload.get("with", {}).get("if-no-files-found") == "error",
            "Only the structural report may be uploaded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        directory = args.root / ".github/workflows"
        for path in sorted(directory.glob("*.y*ml")):
            document = load(path.read_text())
            if path.name == "ci.yml":
                validate_ci(document)
            elif path.name == "release.yml":
                validate_release(document)
            elif path.name == "acceptance.yml":
                validate_acceptance(document)
            else:
                raise ValueError("New workflows require explicit policy review")
        require(all((directory / name).is_file() for name in ("ci.yml", "release.yml", "acceptance.yml")),
                "Required workflows missing")
    except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"Workflow policy rejected: {error}\n")
    print("Workflow policy passed. Repository settings and live acceptance require separate evidence.")


if __name__ == "__main__":
    main()
