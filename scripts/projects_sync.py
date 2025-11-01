#!/usr/bin/env python3
"""
Sync a single Issue/PR into a GitHub Projects (v2) project and print its field values.

Environment variables expected (the workflow sets these):
- GH_TOKEN            : PAT (classic) with "project" scope
                        (or GITHUB_TOKEN with proper perms if using org runner)
- PROJECT_ID          : (preferred) the opaque GraphQL ID (PVT_...) of the target project
- PROJECT_OWNER       : fallback owner login (user or org), e.g. "greta-47"
- PROJECT_NUMBER      : fallback project number (string or int), e.g. "1"
- ISSUE_NUMBER        : number of the Issue/PR to sync
- ISSUE_URL           : (optional) direct https://github.com/owner/repo/{issues|pull}/123
- REPO_OWNER          : repository owner (workflow sets github.repository_owner)
- REPO_NAME           : repository name (or empty; we'll split GITHUB_REPOSITORY if needed)
- GITHUB_REPOSITORY   : "owner/name" (always available; used as fallback for owner/name)
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from typing import Any, Dict, NoReturn, Optional, Tuple

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

Q_GET_PROJECT_FIELDS = """
query($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 50) {
        nodes {
          __typename
          ... on ProjectV2FieldCommon {
            id
            name
          }
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name }
          }
          ... on ProjectV2IterationField {
            id
            name
            configuration { duration startDay }
          }
        }
      }
    }
  }
}
"""

# Uses the *current* ItemFieldValue types
Q_ITEM_FIELD_VALUES = """
query($itemId: ID!) {
  node(id: $itemId) {
    ... on ProjectV2Item {
      id
      fieldValues(first: 50) {
        nodes {
          __typename
          ... on ProjectV2ItemFieldSingleSelectValue {
            field {
              __typename
              ... on ProjectV2SingleSelectField { id name }
            }
            optionId
            name
          }
        }
      }
    }
  }
}
"""

M_UPDATE_FIELD = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: $projectId
      itemId: $itemId
      fieldId: $fieldId
      value: $value
    }
  ) {
    projectV2Item { id }
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
        if t == "ProjectV2ItemFieldSingleSelectValue":
            parsed = {"optionId": v.get("optionId"), "optionName": v.get("name")}

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
    try:
        num = int(number)
    except ValueError:
        die("PROJECT_NUMBER must be an integer-like value")
    rs = client.gql(Q_GET_PROJECT_ID, {"owner": owner, "number": num})
    org = ((rs.get("data") or {}).get("organization") or {}).get("projectV2") or {}
    usr = ((rs.get("data") or {}).get("user") or {}).get("projectV2") or {}
    pid: Optional[str] = org.get("id") or usr.get("id")
    if not pid:
        die(f"Could not resolve project for owner={owner} number={number}")
    return pid


def get_content_id(client: GQLClient, owner: str, repo: str, number: int) -> Tuple[str, str]:
    rs = client.gql(Q_GET_CONTENT_AND_ID, {"owner": owner, "name": repo, "number": number})
    iop = (((rs.get("data") or {}).get("repository") or {}).get("issueOrPullRequest")) or {}
    cid = iop.get("id")
    typ = iop.get("__typename")
    if not cid or not typ:
        die(f"Could not resolve Issue/PR content ID for {owner}/{repo}#{number}")
    return cid, typ


def ensure_item_in_project(client: GQLClient, project_id: str, content_id: str) -> Optional[str]:
    rs = client.gql(M_ADD_ITEM, {"projectId": project_id, "contentId": content_id})
    # If already exists, GH may still return 200 with errors; we'll try to recover gracefully
    if "errors" in rs and rs["errors"]:
        errors_json = json.dumps(rs["errors"], indent=2)
        die(f"GraphQL errors encountered when adding item to project: {errors_json}")
    item_id = ((((rs.get("data") or {}).get("addProjectV2ItemById") or {}).get("item")) or {}).get(
        "id"
    )
    if item_id:
        return item_id
    # Attempt a cheap follow-up: projects don't expose "find item by content" directly here,
    # but we can continue without item_id if GraphQL later allows item(id: ...) via returned id.
    # Many installs return the same id on re-add; when missing, we'll proceed to read
    return None


def get_project_fields(client: GQLClient, project_id: str) -> dict[str, Any]:
    """Fetch field configs (Priority, Status) using inline fragments.
    This avoids union selection errors on ProjectV2 field types."""
    rs = client.gql(Q_GET_PROJECT_FIELDS, {"projectId": project_id})
    fields = (((rs.get("data") or {}).get("node") or {}).get("fields") or {}).get("nodes", [])

    priority_field: dict[str, Any] | None = None
    status_field: dict[str, Any] | None = None

    print("Available fields in project:")
    for f in fields:
        name = f.get("name")
        typ = f.get("__typename")
        print(f"  - {name} ({typ})")
        if typ == "ProjectV2SingleSelectField":
            options = f.get("options", [])
            print(f"    Options: {[o.get('name') for o in options]}")

    for f in fields:
        name = f.get("name")
        typ = f.get("__typename")
        if name == "Priority" and typ == "ProjectV2SingleSelectField":
            priority_field = f
        elif name == "Status" and typ == "ProjectV2SingleSelectField":
            status_field = f

    if not priority_field:
        print("WARNING: Could not find 'Priority' single-select field in project", file=sys.stderr)
        print("Available fields listed above. Continuing without Priority field.", file=sys.stderr)
    else:
        print(f"✓ Found Priority field (ID: {priority_field['id']})")

    if not status_field:
        print("WARNING: Could not find 'Status' single-select field in project", file=sys.stderr)
        print("Available fields listed above. Continuing without Status field.", file=sys.stderr)
    else:
        print(f"✓ Found Status field (ID: {status_field['id']})")

    return {"priority": priority_field, "status": status_field}


def get_item_field_values(client: GQLClient, item_id: str) -> list[dict[str, Any]]:
    """Return current single-select field values for a project item."""
    rs = client.gql(Q_ITEM_FIELD_VALUES, {"itemId": item_id})
    item = rs.get("data", {}).get("node")
    return (item or {}).get("fieldValues", {}).get("nodes", []) if item else []


def set_field_value(
    client: GQLClient, project_id: str, item_id: str, field_id: str, option_id: str
) -> None:
    """Set a single-select field value on a project item."""
    variables = {
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "value": {"singleSelectOptionId": option_id},
    }
    client.gql(M_UPDATE_FIELD, variables)


# ----------------------------
# Main
# ----------------------------
def main():
    token = os.getenv("GH_TOKEN")
    if not token:
        die("GH_TOKEN is required")

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
        die("Could not obtain item_id")

    fields = get_project_fields(client, project_id)
    priority_field = fields.get("priority")
    status_field = fields.get("status")

    p2_option = None
    if priority_field:
        p2_option = next(
            (o for o in priority_field.get("options", []) if o["name"] == "P2 (Normal)"),
            None,
        )
        if p2_option:
            print(f"✓ Found P2 (Normal) option (ID: {p2_option['id']})")
        else:
            print("WARNING: Could not find 'P2 (Normal)' option in Priority field", file=sys.stderr)
            print("Will skip setting Priority field.", file=sys.stderr)

    status_option = None
    status_candidates = ["Todo", "To do", "Backlog", "To Do"]
    if status_field:
        for candidate in status_candidates:
            status_option = next(
                (
                    o
                    for o in status_field.get("options", [])
                    if o["name"].lower() == candidate.lower()
                ),
                None,
            )
            if status_option:
                print(f"✓ Found '{status_option['name']}' option (ID: {status_option['id']})")
                break

        if not status_option:
            print(
                f"WARNING: Could not find any of {status_candidates} in Status field",
                file=sys.stderr,
            )
            print("Will skip setting Status field.", file=sys.stderr)

    print()

    # Only set defaults if unset
    current_values = get_item_field_values(client, item_id)
    priority_set = any((v.get("field") or {}).get("name") == "Priority" for v in current_values)
    status_set = any((v.get("field") or {}).get("name") == "Status" for v in current_values)

    if priority_field and p2_option and not priority_set:
        print("Setting Priority to P2 (Normal)…")
        set_field_value(client, project_id, item_id, priority_field["id"], p2_option["id"])
        print("✓ Priority set")
    elif priority_set:
        print("✓ Priority already set, skipping")
    elif not priority_field:
        print("⊘ Priority field not found, skipping")
    elif not p2_option:
        print("⊘ Priority option not found, skipping")

    if status_field and status_option and not status_set:
        print(f"Setting Status to {status_option['name']}…")
        set_field_value(client, project_id, item_id, status_field["id"], status_option["id"])
        print("✓ Status set")
    elif status_set:
        print("✓ Status already set, skipping")
    elif not status_field:
        print("⊘ Status field not found, skipping")
    elif not status_option:
        print("⊘ Status option not found, skipping")

    print("\n✅ Sync complete!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.HTTPError:
        sys.exit(1)
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        sys.exit(1)
