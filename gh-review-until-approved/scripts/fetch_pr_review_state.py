#!/usr/bin/env python3
"""Fetch a thread-aware GitHub pull request review snapshot via ``gh``."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse


PR_REF_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<number>[1-9][0-9]*)$"
)

QUERY = r"""
query(
  $owner: String!
  $repo: String!
  $number: Int!
  $commentsCursor: String
  $reviewsCursor: String
  $threadsCursor: String
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      url
      title
      state
      isDraft
      reviewDecision
      mergeStateStatus
      updatedAt
      baseRefName
      headRefName
      headRefOid
      headRepository { nameWithOwner }

      comments(first: 100, after: $commentsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          url
          body
          createdAt
          updatedAt
          author { login }
        }
      }

      reviews(first: 100, after: $reviewsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          url
          state
          body
          submittedAt
          author { login }
          commit { oid }
        }
      }

      reviewThreads(first: 100, after: $threadsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          diffSide
          startLine
          startDiffSide
          originalLine
          originalStartLine
          resolvedBy { login }
          comments(first: 100) {
            nodes {
              id
              url
              body
              createdAt
              updatedAt
              author { login }
              pullRequestReview {
                state
                commit { oid }
              }
            }
          }
        }
      }

      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup {
              contexts(first: 100) {
                nodes {
                  __typename
                  ... on CheckRun {
                    name
                    status
                    conclusion
                    detailsUrl
                    startedAt
                    completedAt
                  }
                  ... on StatusContext {
                    context
                    state
                    targetUrl
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


def parse_pr_ref(value: str) -> tuple[str, str, int]:
    """Parse a github.com PR URL or OWNER/REPO#NUMBER reference."""
    match = PR_REF_RE.fullmatch(value.strip())
    if match:
        return match["owner"], match["repo"], int(match["number"])

    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise ValueError("expected https://github.com/OWNER/REPO/pull/NUMBER")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] != "pull" or not parts[3].isdigit() or int(parts[3]) < 1:
        raise ValueError("expected https://github.com/OWNER/REPO/pull/NUMBER")
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts[:2]):
        raise ValueError("owner or repository contains unsupported characters")
    return parts[0], parts[1], int(parts[3])


def run_json(command: list[str], stdin: str | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, input=stdin, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned invalid JSON: {exc}") from exc


def ensure_gh_authenticated() -> None:
    completed = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError("gh authentication failed; run `gh auth login`")


def fetch_page(
    owner: str,
    repo: str,
    number: int,
    comments_cursor: str | None,
    reviews_cursor: str | None,
    threads_cursor: str | None,
) -> dict[str, Any]:
    command = [
        "gh",
        "api",
        "graphql",
        "-F",
        "query=@-",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={number}",
    ]
    for name, cursor in (
        ("commentsCursor", comments_cursor),
        ("reviewsCursor", reviews_cursor),
        ("threadsCursor", threads_cursor),
    ):
        if cursor:
            command.extend(["-F", f"{name}={cursor}"])
    payload = run_json(command, stdin=QUERY)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        identifier = str(item.get("id", ""))
        if identifier and identifier in seen:
            continue
        if identifier:
            seen.add(identifier)
        result.append(item)
    return result


def fetch_all(owner: str, repo: str, number: int) -> dict[str, Any]:
    conversation_comments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    review_threads: list[dict[str, Any]] = []
    comments_cursor: str | None = None
    reviews_cursor: str | None = None
    threads_cursor: str | None = None
    pull_request: dict[str, Any] | None = None

    while True:
        payload = fetch_page(
            owner, repo, number, comments_cursor, reviews_cursor, threads_cursor
        )
        repository = payload.get("data", {}).get("repository")
        if not repository or not repository.get("pullRequest"):
            raise RuntimeError(f"pull request not found: {owner}/{repo}#{number}")
        current = repository["pullRequest"]
        if pull_request is None:
            pull_request = {
                key: value
                for key, value in current.items()
                if key not in {"comments", "reviews", "reviewThreads", "commits"}
            }
            pull_request["owner"] = owner
            pull_request["repo"] = repo
            commit_nodes = current.get("commits", {}).get("nodes") or []
            pull_request["headCommit"] = commit_nodes[0]["commit"] if commit_nodes else None

        comments = current["comments"]
        current_reviews = current["reviews"]
        threads = current["reviewThreads"]
        conversation_comments.extend(comments.get("nodes") or [])
        reviews.extend(current_reviews.get("nodes") or [])
        review_threads.extend(threads.get("nodes") or [])

        comments_cursor = (
            comments["pageInfo"]["endCursor"] if comments["pageInfo"]["hasNextPage"] else None
        )
        reviews_cursor = (
            current_reviews["pageInfo"]["endCursor"]
            if current_reviews["pageInfo"]["hasNextPage"]
            else None
        )
        threads_cursor = (
            threads["pageInfo"]["endCursor"] if threads["pageInfo"]["hasNextPage"] else None
        )
        if not any((comments_cursor, reviews_cursor, threads_cursor)):
            break

    assert pull_request is not None
    reviews = deduplicate(reviews)
    review_threads = deduplicate(review_threads)
    head_oid = pull_request.get("headRefOid")
    formal_head_approvals = [
        review
        for review in reviews
        if review.get("state") == "APPROVED"
        and (review.get("commit") or {}).get("oid") == head_oid
    ]
    active_threads = [
        thread
        for thread in review_threads
        if not thread.get("isResolved") and not thread.get("isOutdated")
    ]
    return {
        "pull_request": pull_request,
        "conversation_comments": deduplicate(conversation_comments),
        "reviews": reviews,
        "review_threads": review_threads,
        "derived": {
            "active_thread_ids": [thread.get("id") for thread in active_threads],
            "formal_head_approval_review_ids": [
                review.get("id") for review in formal_head_approvals
            ],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", help="GitHub PR URL or OWNER/REPO#NUMBER")
    parser.add_argument(
        "--parse-only", action="store_true", help="parse the PR reference without calling gh"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        owner, repo, number = parse_pr_ref(args.pr)
        if args.parse_only:
            result: dict[str, Any] = {"owner": owner, "repo": repo, "number": number}
        else:
            ensure_gh_authenticated()
            result = fetch_all(owner, repo, number)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
