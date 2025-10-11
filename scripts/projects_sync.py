#!/usr/bin/env python3
"""
Sync a single Issue/PR into a GitHub Projects (v2) project and print its field values.

Environment variables expected (the workflow sets these):
- GH_TOKEN            : PAT (classic) with "project" scope
-                         (or GITHUB_TOKEN with proper perms if using org runner)
- PROJECT_ID          : (preferred) the opaque GraphQL ID (PVT_...) of the target project
- PROJECT_OWNER       : fallback owner login (user or org), e.g. "greta-47"
- PROJECT_NUMBER      : fallback project number (string or int), e.g. "1"
- ISSUE_NUMBER        : number of the Issue/PR to sync
- ISSUE_URL           : (optional) direct https://github.com/owner/repo/{issues|pull}/123
- REPO_OWNER          : repository owner (workflow sets github.repository_owner)
- REPO_NAME           : repository name (or empty; we’ll split GITHUB_REPOSITORY if needed)
- GITHUB_REPOSITORY   : "owner/name" (always available; used as fallback for owner/name)
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from typing import Any, Dict, NoReturn, Optional, Tuple, cast

import requests  # type: ignore[import-untyped]

GQL_ENDPOINT = "https://api.github.com/graphql"


# ----------------------------
# Small GraphQL client helpers
# ----------------------------
class GQLClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            }
        )

    def gql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.post(GQL_ENDPOINT, json={"query": query, "variables": variables})
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            print(f"[GraphQL HTTPError] {e}\nResponse: {r.text}", file=sys.stderr)
            raise
        payload = r.json()
        if "errors" in payload and payload["errors"]:
            print("GraphQL errors:")
            print(json.dumps(payload["errors"], indent=2))
        return payload


# ----------------------------
# Query / mutation strings
# ----------------------------

Q_GET_PROJECT_ID = """
query($owner: String!, $number: Int!) {
  organization(login: $owner) {
    projectV2(number: $number) { id title }
  }
  user(login: $owner) {
    projectV2(number: $number) { id title }
  }
}
"""

Q_GET_CONTENT_AND_ID = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issueOrPullRequest(number: $number) {
      __typename
      ... on Issue { id url number title }
      ... on PullRequest { id url number title }
    }
  }
}
"""

M_ADD_ITEM = """
mutation($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item { id }
  }
}
"""

# Uses the *current* ItemFieldValue types
Q_ITEM_FIELD_VALUES = """
query($projectId: ID!, $itemId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      item(id: $itemId) {
        id
        fieldValues(first: 50) {
          nodes {
            __typename
            ... on ProjectV2ItemFieldSingleSelectValue  { field { id name } optionId name }
            ... on ProjectV2ItemFieldDateValue          { field { id name } value }
            ... on ProjectV2ItemFieldTextValue          { field { id name } text }
            ... on ProjectV2ItemFieldNumberValue        { field { id name } number }
            ... on ProjectV2ItemFieldTitleValue         { field { id name } title }
            ... on ProjectV2ItemFieldRepositoryValue    {
              field { id name }
              repository { nameWithOwner }
            }
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------
# Parser helper for fieldValues (drop-in)
# ---------------------------------------
def parse_project_item_field_values(item: dict) -> dict:
    """
    Input:  'item' object from the GraphQL response.
    Output:
      {
        'by_name': { field_name: parsed_value, ... },
        'by_id':   { field_id:   parsed_value, ... },
        'meta':    { field_name: {'id': field_id, 'typename': typename}, ... }
      }
    """
    out_by_name, out_by_id, meta = {}, {}, {}
    nodes = (((item or {}).get("fieldValues") or {}).get("nodes")) or []

    for v in nodes:
        t = v.get("__typename")
        f = v.get("field") or {}
        field_id = f.get("id")
        field_name = f.get("name")
        if not field_id or not field_name:
            continue

        parsed = None
        if t == "ProjectV2ItemFieldTextValue":
            parsed = v.get("text")
        elif t == "ProjectV2ItemFieldNumberValue":
            parsed = v.get("number")
        elif t == "ProjectV2ItemFieldDateValue":
            parsed = v.get("value")
        elif t == "ProjectV2ItemFieldTitleValue":
            parsed = v.get("title")
        elif t == "ProjectV2ItemFieldSingleSelectValue":
            parsed = {"optionId": v.get("optionId"), "optionName": v.get("name")}
        elif t == "ProjectV2ItemFieldAssigneesValue":
            parsed = [n.get("login") for n in (v.get("assignees") or {}).get("nodes", [])]
        elif t == "ProjectV2ItemFieldLabelValue":
            parsed = [n.get("name") for n in (v.get("labels") or {}).get("nodes", [])]
        elif t == "ProjectV2ItemFieldRepositoryValue":
            parsed = (v.get("repository") or {}).get("nameWithOwner")
        elif t == "ProjectV2ItemFieldMilestoneValue":
            parsed = (v.get("milestone") or {}).get("title")
        elif t == "ProjectV2ItemFieldPullRequestValue":
            prs = (v.get("pullRequests") or {}).get("nodes", [])
            parsed = [{"number": pr.get("number"), "title": pr.get("title")} for pr in prs]
        elif t == "ProjectV2ItemFieldTrackedByValue":
            parsed = v.get("createdAt")

        out_by_name[field_name] = parsed
        out_by_id[field_id] = parsed
        meta[field_name] = {"id": field_id, "typename": t}

    return {"by_name": out_by_name, "by_id": out_by_id, "meta": meta}


# ----------------------------
# Utility helpers
# ----------------------------
def die(msg: str, code: int = 1) -> NoReturn:
    print(msg, file=sys.stderr)
    sys.exit(code)


def coalesce(*vals):
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def split_repo(
    owner: Optional[str], name: Optional[str], repo_env: Optional[str]
) -> Tuple[str, str]:
    if owner and name:
        return owner, name
    if repo_env and "/" in repo_env:
        o, n = repo_env.split("/", 1)
        return o, n
    die("REPO_OWNER/REPO_NAME or GITHUB_REPOSITORY must be provided")


def parse_issue_number(issue_number: Optional[str], issue_url: Optional[str]) -> int:
    if issue_number:
        try:
            return int(issue_number)
        except ValueError:
            die(f"ISSUE_NUMBER must be an integer-like value, got: {issue_number!r}")
    if issue_url:
        m = re.search(r"/(issues|pull)/(\d+)$", issue_url)
        if m:
            return int(m.group(2))
    die("ISSUE_NUMBER or ISSUE_URL must be provided")


def resolve_project_id(
    client: GQLClient, project_id: Optional[str], owner: Optional[str], number: Optional[str]
) -> str:
    if project_id:
        return project_id
    if not owner or not number:
        die("PROJECT_ID is missing and fallback (PROJECT_OWNER + PROJECT_NUMBER) is incomplete.")
    number_str = number
    try:
        num = int(number_str)
    except ValueError:
        die("PROJECT_NUMBER must be an integer-like value")
    rs = client.gql(Q_GET_PROJECT_ID, {"owner": owner, "number": num})
    org = ((rs.get("data") or {}).get("organization") or {}).get("projectV2") or {}
    usr = ((rs.get("data") or {}).get("user") or {}).get("projectV2") or {}
    pid = org.get("id") or usr.get("id")
    if not pid:
        die(f"Could not resolve project for owner={owner} number={number}")
    return cast(str, pid)


def get_content_id(client: GQLClient, owner: str, repo: str, number: int) -> Tuple[str, str]:
    rs = client.gql(Q_GET_CONTENT_AND_ID, {"owner": owner, "name": repo, "number": number})
    iop = (((rs.get("data") or {}).get("repository") or {}).get("issueOrPullRequest")) or {}
    cid_any = iop.get("id")
    typ_any = iop.get("__typename")
    if not cid_any:
        die(f"Could not resolve Issue/PR content ID for {owner}/{repo}#{number}")
    cid = cast(str, cid_any)
    typ = cast(str, typ_any)
    return cid, typ


def ensure_item_in_project(client: GQLClient, project_id: str, content_id: str) -> Optional[str]:
    rs = client.gql(M_ADD_ITEM, {"projectId": project_id, "contentId": content_id})
    # If already exists, GH may still return 200 with errors; we’ll try to recover gracefully
    if "errors" in rs and rs["errors"]:
        die(
            "GraphQL errors encountered when adding item to project: "
            f"{json.dumps(rs['errors'], indent=2)}"
        )
    item_id = ((((rs.get("data") or {}).get("addProjectV2ItemById") or {}).get("item")) or {}).get(
        "id"
    )
    if item_id:
        return item_id
    # Attempt a cheap follow-up: projects don’t expose “find item by content” directly here,
    # but we can continue without item_id if GraphQL later allows item(id: ...) via returned id.
    # Many installs return the same id on re-add; when missing, we’ll proceed to read fields
    return None


def fetch_item_fields(client: GQLClient, project_id: str, item_id: str) -> dict:
    rs = client.gql(Q_ITEM_FIELD_VALUES, {"projectId": project_id, "itemId": item_id})
    item = (((rs.get("data") or {}).get("node") or {}).get("item")) or {}
    return item


# ----------------------------
# Main
# ----------------------------
def main():
    token = os.getenv("GH_TOKEN")
    if not token:
        die("GH_TOKEN is required")
    assert token is not None

    project_id_env = os.getenv("PROJECT_ID")
    project_owner = os.getenv("PROJECT_OWNER")
    project_number = os.getenv("PROJECT_NUMBER")

    issue_number_env = os.getenv("ISSUE_NUMBER")
    issue_url = os.getenv("ISSUE_URL")

    repo_owner = os.getenv("REPO_OWNER")
    repo_name = os.getenv("REPO_NAME")
    gh_repo = os.getenv("GITHUB_REPOSITORY")

    # Derive repo owner/name and issue number
    owner, name = split_repo(repo_owner, repo_name, gh_repo)
    number = parse_issue_number(issue_number_env, issue_url)

    client = GQLClient(token)

    # Resolve project id
    project_id = resolve_project_id(client, project_id_env, project_owner, project_number)
    print(f"[info] Project ID: {project_id}")

    # Resolve content (Issue/PR) id
    content_id, tp = get_content_id(client, owner, name, number)
    print(f"[info] Content: {owner}/{name}#{number} ({tp}), node id={content_id}")

    # Ensure item exists in project
    item_id = ensure_item_in_project(client, project_id, content_id)
    if item_id:
        print(f"[info] Project item ensured: {item_id}")
    else:
        print(
            textwrap.dedent("""\
            [warn] Could not obtain item id from addProjectV2ItemById (it may already exist).
            If the next step fails, verify the item exists in the project.
        """).strip()
        )

    # If we didn’t get the item id, we can’t query item(id: ...). In practice, addProjectV2ItemById
    # returns one even for repeats—but if it didn’t, we’ll stop here with a soft
    if not item_id:
        print("[soft-exit] Item presence attempted; nothing else to update. Exiting 0.")
        return 0

    # Fetch and parse field values
    item = fetch_item_fields(client, project_id, item_id)
    parsed = parse_project_item_field_values(item)

    # Print a compact summary to logs (useful for debugging)
    print("[fields/by_name]")
    for k, v in parsed["by_name"].items():
        print(f"  - {k}: {json.dumps(v, ensure_ascii=False)}")

    # If you have business rules to set fields, this is where you’d apply them.

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.HTTPError:
        sys.exit(1)
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        sys.exit(1)
