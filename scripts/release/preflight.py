#!/usr/bin/env python3
"""Read-only publisher checks. Missing repository protection evidence rejects release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from package import PUBLISHER, REPOSITORY, SHA, ReleaseRequest, git, run, strict_object

GITHUB_ACTIONS_APP_ID = 15368
REQUIRED_CHECKS = {"full-linux", "full-macos", "workflow-policy"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def api(endpoint, pages=False):
    args = ["gh", "api", "--hostname", "github.com", "--method", "GET",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{REPOSITORY}/{endpoint}"]
    if pages:
        args += ["--paginate", "--slurp"]
    data = run(args)
    require(len(data) <= 1024 * 1024, "Protection API response exceeds limit")
    return json.loads(data, object_pairs_hook=strict_object)


def validate_environment(environment, policy_pages, name, tag="v0.2.0"):
    require(type(environment) is dict and environment.get("name") == name
            and type(environment.get("id")) is int and environment["id"] > 0,
            "Required release environment does not exist")
    require(environment.get("deployment_branch_policy") == {
        "protected_branches": False, "custom_branch_policies": True},
        "Environment must restrict deployments to explicit version tags")
    rules = environment.get("protection_rules")
    require(type(rules) is list and all(type(rule) is dict for rule in rules),
            "Environment protection rules missing")
    review = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    require(len(review) == 1 and review[0].get("prevent_self_review") is False,
            "Release requires explicit sole-maintainer approval with self-review allowed")
    reviewers = review[0].get("reviewers")
    require(type(reviewers) is list and len(reviewers) == 1, "Exactly one owner reviewer required")
    for reviewer in reviewers:
        require(type(reviewer) is dict and reviewer.get("type") == "User"
                and type(reviewer.get("reviewer")) is dict
                and type(reviewer["reviewer"].get("id")) is int and reviewer["reviewer"]["id"] == 82675328,
                "Release reviewer must be owner 82675328")
    require(type(policy_pages) is list and len(policy_pages) > 0, "Deployment policy pages missing")
    policies = []
    for page in policy_pages:
        require(type(page) is dict and type(page.get("branch_policies")) is list
                and type(page.get("total_count")) is int and page["total_count"] == 1, "Exactly one deployment restriction required")
        policies.extend(page["branch_policies"])
    require(len(policies) == 1 and type(policies[0]) is dict
            and policies[0].get("name") == tag and policies[0].get("type") == "tag"
            and type(policies[0].get("id")) is int and policies[0]["id"] > 0,
            "Only the exact requested tag deployment restriction is accepted")


def validate_main(branch, rule_pages):
    require(type(branch) is dict and branch.get("name") == "main" and branch.get("protected") is True,
            "main must be protected")
    commit = branch.get("commit")
    require(type(commit) is dict and type(commit.get("sha")) is str and SHA.fullmatch(commit["sha"]),
            "main commit identity missing")
    require(type(rule_pages) is list and len(rule_pages) > 0
            and all(type(page) is list for page in rule_pages), "Active main rules missing")
    rules = [rule for page in rule_pages for rule in page]
    require(all(type(rule) is dict for rule in rules), "Invalid active main rule")
    reviews = [r.get("parameters") for r in rules if r.get("type") == "pull_request"]
    require(any(type(p) is dict and type(p.get("required_approving_review_count")) is int
                and p["required_approving_review_count"] == 0
                and p.get("dismiss_stale_reviews_on_push") is True
                and p.get("require_last_push_approval") is False
                and p.get("required_review_thread_resolution") is True for p in reviews),
            "Active main rules must require PRs and resolved threads under sole-maintainer policy")
    checks = [r.get("parameters") for r in rules if r.get("type") == "required_status_checks"]
    accepted = False
    for parameters in checks:
        if type(parameters) is not dict or parameters.get("strict_required_status_checks_policy") is not True:
            continue
        statuses = parameters.get("required_status_checks")
        if type(statuses) is not list:
            continue
        contexts = {s.get("context") for s in statuses if type(s) is dict
                    and type(s.get("context")) is str and type(s.get("integration_id")) is int
                    and s["integration_id"] == GITHUB_ACTIONS_APP_ID}
        if REQUIRED_CHECKS <= contexts:
            accepted = True
    require(accepted, "Active main rules must require current Linux, macOS, and workflow policy checks")
    return commit["sha"]


def validate_tag_rules(ruleset, request):
    require(type(ruleset) is dict and ruleset.get("target") == "tag"
            and ruleset.get("enforcement") == "active"
            and ruleset.get("source_type") == "Repository" and ruleset.get("source") == REPOSITORY,
            "Active repository tag rules required")
    conditions = ruleset.get("conditions")
    require(type(conditions) is dict and type(conditions.get("ref_name")) is dict,
            "Tag rules must have explicit ref conditions")
    refs = conditions["ref_name"]
    require(refs.get("exclude") == [] and refs.get("include") in (
        ["refs/tags/v*"], [f"refs/tags/{request.tag}"], ["~ALL"]),
        "Tag preservation rules must cover the exact version tag without exclusions")
    rules = ruleset.get("rules")
    require(type(rules) is list and all(type(rule) is dict for rule in rules)
            and {"update", "deletion"} <= {rule.get("type") for rule in rules},
            "Version tags must refuse updates and deletion")
    if "bypass_actors" in ruleset:
        require(ruleset["bypass_actors"] == [], "Tag preservation must not grant bypass actors")


def check_tag_rules(request):
    pages = api("rulesets?per_page=100", True)
    require(type(pages) is list and pages and all(type(page) is list for page in pages),
            "Tag ruleset pages missing")
    candidates = [rule for page in pages for rule in page
                  if type(rule) is dict and rule.get("target") == "tag"
                  and rule.get("enforcement") == "active" and rule.get("source") == REPOSITORY]
    require(candidates, "Active tag preservation ruleset missing")
    accepted = False
    for candidate in candidates:
        identifier = candidate.get("id")
        require(type(identifier) is int and identifier > 0, "Tag ruleset identity missing")
        detail = api(f"rulesets/{identifier}")
        require(type(detail) is dict and detail.get("id") == identifier, "Tag ruleset response identity mismatch")
        try:
            validate_tag_rules(detail, request)
            accepted = True
        except ValueError:
            continue
    require(accepted, "No active ruleset preserves the version tag")


def check_source_ci(request):
    workflow = api("actions/workflows/ci.yml")
    require(type(workflow) is dict and workflow.get("path") == ".github/workflows/ci.yml"
            and workflow.get("state") == "active" and type(workflow.get("id")) is int
            and workflow["id"] > 0, "Required CI workflow identity missing")
    pages = api(f"actions/workflows/ci.yml/runs?head_sha={request.source_sha}&event=push&per_page=100", True)
    require(type(pages) is list and pages and all(type(page) is dict
            and type(page.get("workflow_runs")) is list for page in pages), "Source CI runs missing")
    runs = [run for page in pages for run in page["workflow_runs"]]
    require(runs and all(type(run) is dict and type(run.get("id")) is int for run in runs),
            "Source CI run identities missing")
    evidence = max(runs, key=lambda run: run["id"])
    require(evidence.get("workflow_id") == workflow["id"] and evidence.get("path") == ".github/workflows/ci.yml"
            and evidence.get("head_sha") == request.source_sha and evidence.get("event") == "push"
            and evidence.get("status") == "completed" and evidence.get("conclusion") == "success"
            and type(evidence.get("run_attempt")) is int and evidence["run_attempt"] > 0
            and type(evidence.get("check_suite_id")) is int and evidence["check_suite_id"] > 0,
            "Latest exact-source CI push run must complete successfully")
    for field in ("repository", "head_repository"):
        repository = evidence.get(field)
        require(type(repository) is dict and type(repository.get("id")) is int
                and str(repository["id"]) == PUBLISHER.repository_id
                and repository.get("full_name") == REPOSITORY, "CI repository identity mismatch")
    job_pages = api(f"actions/runs/{evidence['id']}/attempts/{evidence['run_attempt']}/jobs?per_page=100", True)
    require(type(job_pages) is list and job_pages and all(type(page) is dict
            and type(page.get("jobs")) is list for page in job_pages), "Source CI jobs missing")
    jobs = [job for page in job_pages for job in page["jobs"]]
    require(all(type(job) is dict for job in jobs), "Invalid source CI job")
    for name in REQUIRED_CHECKS:
        matches = [job for job in jobs if job.get("name") == name]
        require(len(matches) == 1, "Every required CI job must occur exactly once")
        job = matches[0]
        require(job.get("status") == "completed" and job.get("conclusion") == "success"
                and job.get("head_sha") == request.source_sha and job.get("run_id") == evidence["id"]
                and job.get("run_attempt") == evidence["run_attempt"], "Required exact-source CI job failed")
        url = job.get("check_run_url")
        match = re.fullmatch(r"https://api\.github\.com/repos/ddv1982/tailmux/check-runs/([1-9][0-9]*)", url or "")
        require(match is not None, "CI check-run identity missing")
        check = api(f"check-runs/{match[1]}")
        require(type(check) is dict and check.get("id") == int(match[1]) and check.get("name") == name
                and check.get("head_sha") == request.source_sha and check.get("status") == "completed"
                and check.get("conclusion") == "success" and type(check.get("app")) is dict
                and type(check["app"].get("id")) is int and check["app"]["id"] == GITHUB_ACTIONS_APP_ID
                and type(check.get("check_suite")) is dict
                and check["check_suite"].get("id") == evidence["check_suite_id"],
                "Required CI check must be a successful exact-source GitHub Actions check")
    return evidence["id"]


def live_waiver(raw, request):
    encoded = raw.encode("utf-8")
    require(len(encoded) <= 4096, "Live-only waiver exceeds limit")
    if raw:
        reasons = {
            "v0.2.0": "User explicitly requested stable 0.2.0 without waiting for the live test.",
            "v0.2.1": "Release owner accepts live SSH coverage as NOT_VERIFIED for the v0.2.1 Linux migration patch.",
            "v0.2.2": "Release owner accepts live SSH coverage as NOT_VERIFIED for the v0.2.2 optional Sentry reporting release.",
            "v0.2.3": "Release owner accepts live SSH coverage as NOT_VERIFIED for the v0.2.3 daemon selection patch.",
            "v0.3.0": "Release owner accepts live SSH coverage as NOT_VERIFIED for the v0.3.0 installation recovery and saved daemon selection release.",
        }
        require(request.tag in reasons, "Live-only waiver is not implemented for this release")
        expected = {"schema": "tailmux-live-only-waiver-v1", "repository": REPOSITORY,
                    "tag": request.tag, "source_sha": request.source_sha, "scope": "live-acceptance-only",
                    "live_acceptance": "NOT_VERIFIED", "operator_id": 82675328,
                    "reason": reasons[request.tag]}
        actual = json.loads(raw, object_pairs_hook=strict_object)
        require(type(actual) is dict and actual == expected
                and all(type(actual[key]) is type(value) for key, value in expected.items()),
                "Only the exact-source and exact-tag live-only waiver is accepted")
    return hashlib.sha256(encoded).hexdigest()


def identity(request, root):
    expected = {
        "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_EVENT_NAME": "push", "GITHUB_REF_TYPE": "tag",
        "GITHUB_REF": f"refs/tags/{request.tag}", "GITHUB_REF_NAME": request.tag,
        "GITHUB_SHA": request.source_sha, "GITHUB_WORKFLOW_SHA": request.source_sha,
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/release.yml@refs/tags/{request.tag}",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }
    for key, value in expected.items():
        require(os.environ.get(key) == value, f"Unexpected publisher identity: {key}")
    require(git(root, "rev-parse", "HEAD").decode().strip() == request.source_sha,
            "Checkout does not match independently expected source")
    require(git(root, "rev-parse", f"refs/tags/{request.tag}^{{commit}}").decode().strip() == request.source_sha,
            "Peeled tag does not match independently expected source")


def preflight(request, root, environment, expected_main=None):
    identity(request, root)
    validate_environment(api(f"environments/{environment}"),
                         api(f"environments/{environment}/deployment-branch-policies?per_page=100", True),
                         environment, request.tag)
    main_sha = validate_main(api("branches/main"), api("rules/branches/main?per_page=100", True))
    if expected_main is not None:
        require(main_sha == expected_main, "Reviewed main changed since preflight")
    git(root, "merge-base", "--is-ancestor", request.source_sha, main_sha)
    check_tag_rules(request)
    check_source_ci(request)
    return main_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--environment", default="release")
    parser.add_argument("--main-sha")
    parser.add_argument("--waiver-sha256")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        require(re.fullmatch(r"[A-Za-z0-9_-]+", args.environment), "Invalid environment name")
        require(args.main_sha is None or SHA.fullmatch(args.main_sha), "Invalid captured main SHA")
        request = ReleaseRequest(args.tag, args.source_sha)
        waiver_sha = live_waiver(os.environ.get("RELEASE_LIVE_ONLY_WAIVER", ""), request)
        require(args.waiver_sha256 is None or args.waiver_sha256 == waiver_sha,
                "Live-only waiver changed since preflight")
        main_sha = preflight(request, args.root, args.environment, args.main_sha)
        output = (f"main_sha={main_sha}\nsource_sha={request.source_sha}\ntag={request.tag}\n"
                  f"waiver_sha256={waiver_sha}\n")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.write(output)
        print(output, end="")
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Release preflight rejected: {error}\n")


if __name__ == "__main__":
    main()
