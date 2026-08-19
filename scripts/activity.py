#!/usr/bin/env python3

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.github.com/graphql"

LOGIN = "invariantengineering"
LEX_ORG = "LexLatam-ai"


def graphql(query: str, variables: dict) -> dict:
    token = os.environ["ACTIVITY_TOKEN"]

    payload = json.dumps(
        {
            "query": query,
            "variables": variables,
        }
    ).encode()

    request = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "invariant-public-activity",
        },
    )

    with urllib.request.urlopen(request) as response:
        result = json.load(response)

    if "errors" in result:
        raise RuntimeError(json.dumps(result["errors"], indent=2))

    return result["data"]


def get_org_id(org_login: str) -> str:
    data = graphql(
        """
        query($login: String!) {
          organization(login: $login) {
            id
          }
        }
        """,
        {"login": org_login},
    )

    org = data.get("organization")

    if not org:
        raise RuntimeError(f"Could not resolve organization: {org_login}")

    return org["id"]


def get_contributions(org_id: str) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=365)

    variables = {
        "login": LOGIN,
        "from": start.isoformat().replace("+00:00", "Z"),
        "to": now.isoformat().replace("+00:00", "Z"),
        "orgId": org_id,
    }

    data = graphql(
        """
        query(
          $login: String!,
          $from: DateTime!,
          $to: DateTime!,
          $orgId: ID!
        ) {
          user(login: $login) {
            all: contributionsCollection(
              from: $from,
              to: $to
            ) {
              ...Stats
            }

            lexlatam: contributionsCollection(
              from: $from,
              to: $to,
              organizationID: $orgId
            ) {
              ...Stats
            }
          }
        }

        fragment Stats on ContributionsCollection {
          contributionCalendar {
            totalContributions

            weeks {
              contributionDays {
                contributionCount
              }
            }
          }

          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          totalRepositoriesWithContributedCommits
        }
        """,
        variables,
    )

    user = data.get("user")

    if not user:
        raise RuntimeError(f"Could not resolve GitHub user: {LOGIN}")

    return {
        "timestamp": now,
        "all": user["all"],
        "lexlatam": user["lexlatam"],
    }


def summarize(collection: dict) -> dict:
    days = [
        day
        for week in collection["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]

    return {
        "contributions": collection["contributionCalendar"]["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "prs": collection["totalPullRequestContributions"],
        "reviews": collection["totalPullRequestReviewContributions"],
        "issues": collection["totalIssueContributions"],
        "repos": collection["totalRepositoriesWithContributedCommits"],
        "active_days": sum(
            1
            for day in days
            if day["contributionCount"] > 0
        ),
    }


def print_stats(all_stats: dict, lex_stats: dict) -> None:
    print()
    print("Trailing 365-day GitHub activity")
    print("=" * 40)

    for name, stats in [
        ("All activity", all_stats),
        ("LexLatam.ai", lex_stats),
    ]:
        print()
        print(name)
        print("-" * len(name))
        print(f"Contributions: {stats['contributions']:,}")
        print(f"Commits:       {stats['commits']:,}")
        print(f"Pull requests: {stats['prs']:,}")
        print(f"Reviews:       {stats['reviews']:,}")
        print(f"Issues:        {stats['issues']:,}")
        print(f"Active days:   {stats['active_days']:,}")
        print(f"Repos:         {stats['repos']:,}")


def row(name: str, stats: dict) -> str:
    return (
        f"| {name} "
        f"| {stats['contributions']:,} "
        f"| {stats['commits']:,} "
        f"| {stats['prs']:,} "
        f"| {stats['reviews']:,} "
        f"| {stats['issues']:,} "
        f"| {stats['active_days']:,} "
        f"| {stats['repos']:,} |"
    )


def update_readme(
    all_stats: dict,
    lex_stats: dict,
    timestamp: datetime,
) -> None:
    block = f"""<!-- activity:start -->
### Trailing 365 days

| Scope | Contributions | Commits | PRs | Reviews | Issues | Active days | Repos |
|---|---:|---:|---:|---:|---:|---:|---:|
{row("All current work", all_stats)}
{row("LexLatam.ai", lex_stats)}

_Updated {timestamp.date().isoformat()} from GitHub contribution data. Private repository names, source code, commit messages, issue contents, and PR contents are not published._
<!-- activity:end -->"""

    path = Path("README.md")
    readme = path.read_text(encoding="utf-8")

    updated = re.sub(
        r"<!-- activity:start -->.*?<!-- activity:end -->",
        block,
        readme,
        flags=re.DOTALL,
    )

    if updated == readme:
        raise RuntimeError(
            "README activity markers were not found or nothing changed."
        )

    path.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Update README.md. Without this option, only print metrics.",
    )

    args = parser.parse_args()

    org_id = get_org_id(LEX_ORG)
    result = get_contributions(org_id)

    all_stats = summarize(result["all"])
    lex_stats = summarize(result["lexlatam"])

    print_stats(all_stats, lex_stats)

    if args.write:
        update_readme(
            all_stats,
            lex_stats,
            result["timestamp"],
        )

        print()
        print("README.md updated.")


if __name__ == "__main__":
    main()