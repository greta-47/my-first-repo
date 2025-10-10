#!/usr/bin/env python3
"""
Sync issues and pull requests to a GitHub Project V2.

Flow:
  1) Resolve Project ID (env PROJECT_ID, else user(login)+number)
  2) Discover field IDs (Priority, Stage) using inline fragments
  3) Upsert Issue/PR item into the Project
  4) Set defaults: Priority=P2 (Normal), Stage=Later (only if unset)

Security:
  - Reads GH_TOKEN from env (PAT classic with 'repo' + 'project')
  - Logs only IDs/URLs (no secrets)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

GQL_URL = "https://api.github.com/graphql"


# -----------------------------
# GraphQL helpers
# -----------------------------
def _token() -> str:
    tok = os.environ.get("GH_TOKEN")
    if not tok:
        print("ERROR: GH_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)
    return tok


def graphql_request(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL request against GitHub; exit on 401 or GraphQL errors."""
    headers = {
        "Authorization": f"Bearer { _token() }",          # PAT classic
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(GQL_URL, headers=headers, json=payload, timeout=30)

    # Hard auth failure (HTTP 401)
    if resp.status_code == 401:
        print("ERROR: 401 Unauthorized from GitHub GraphQL (check PAT classic + scopes: repo, project).", file=sys.stderr)
        sys.exit(1)

    resp.raise_for_status()
    data = resp.json()

    # GraphQL-level errors come back as 200 with "errors"
    if data.get("errors"):
        print("GraphQL errors:", file=sys.stderr)
        print(json.dumps(data["errors"], indent=2), file=sys.stderr)
        sys.exit(1)

    return data


def graphql_whoami() -> None:
    """Preflight: confirm token identity (useful diagnostics)."""
    q = "query { viewer { login } rateLimit { remaining } }"
    data = graphql_request(q)
    viewer = data["data"]["viewer"]["login"]
    remaining = data["data"]["rateLimit"]["remaining"]
    print(f"✓ Auth OK as {viewer}; rateLimit.remaining={remaining}")


# -----------------------------
# Project discovery
# -----------------------------
def get_project_id() -> str:
    """
    Prefer PROJECT_ID from env; otherwise resolve from owner+number (user project).
    Requires env: PROJECT_OWNER, PROJECT_NUMBER when PROJECT_ID is absent.
    """
    pid = os.environ.get("PROJECT_ID")
    if pid:
        return pid

    owner = os.environ["PROJECT_OWNER"]
    number = int(os.environ.get("PROJECT_NUMBER", "1"))

    q = """
    query($login:String!, $number:Int!){
      user(login:$login){
        projectV2(number:$number){ id title }
      }
    }"""
    data = graphql_request(q, {"login": owner, "number": number})
    try:
        proj = data["data"]["user"]["projectV2"]
        project_id = proj["id"]
        title = proj.get("title", "<untitled>")
        print(f"✓ Resolved project: {title} (ID: {project_id})")
        return project_id
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not resolve Project ID for {owner} #{number}: {e}", file=sys.stderr)
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)


def get_project_fields(project_id: str) -> dict[str, Any]:
    """Fetch field configs (Priority, Stage) with inline fragments to avoid union selection errors."""
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 50) {
            nodes {
              __typename
              # Common name/id on all field types
              ... on ProjectV2FieldCommon {
                id
                name
              }
              # Single-select fields expose options
              ... on ProjectV2SingleSelectField {
                id
                name
                options { id name }
              }
              # Include other concrete types to satisfy the union (even if unused)
              ... on ProjectV2IterationField { id name }
              ... on ProjectV2DateField { id name }
              ... on ProjectV2TextField { id name }
              ... on ProjectV2NumberField { id name }
              ... on ProjectV2RepositoryField { id name }
              ... on ProjectV2TitleField { id name }
              ... on ProjectV2AssigneesField { id name }
              ... on ProjectV2LabelsField { id name }
              ... on ProjectV2MilestoneField { id name }
              ... on ProjectV2TrackedByField { id name }
              ... on ProjectV2LinkedPullRequestsField { id name }
            }
          }
        }
      }
    }
    """
    data = graphql_request(query, {"projectId": project_id})
    fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", []) or []

    priority_field: dict[str, Any] | None = None
    stage_field: dict[str, Any] | None = None

    for f in fields:
        name = f.get("name")
        typ = f.get("__typename")
        if name == "Priority" and typ == "ProjectV2SingleSelectField":
            priority_field = f
        elif name == "Stage" and typ == "ProjectV2SingleSelectField":
            stage_field = f

    if not priority_field:
        print("ERROR: Could not find 'Priority' single-select field in project", file=sys.stderr)
        sys.exit(1)
    if not stage_field:
        print("ERROR: Could not find 'Stage' single-select field in project", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Found Priority field (ID: {priority_field['id']})")
    print(f"✓ Found Stage field (ID: {stage_field['id']})")

    return {"priority": priority_field, "stage": stage_field}


# -----------------------------
# Item discovery & mutation
# -----------------------------
def get_item_node_id(repo_owner: str, repo_name: str, issue_number: str) -> str:
    """Return the node ID for an issue or pull request by number."""
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        issueOrPullRequest(number: $number) {
          ... on Issue { id }
          ... on PullRequest { id }
        }
      }
    }
    """
    data = graphql_request(query, {"owner": repo_owner, "name": repo_name, "number": int(issue_number)})
    node = data.get("data", {}).get("repository", {}).get("issueOrPullRequest")
    if not node or "id" not in node:
        print(f"ERROR: Could not find issue/PR #{issue_number}", file=sys.stderr)
        sys.exit(1)
    nid = node["id"]
    print(f"✓ Found issue/PR #{issue_number} (ID: {nid})")
    return nid


def add_item_to_project(project_id: str, content_id: str) -> str:
    """Add an issue/PR to the project and return the project item ID."""
    query = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: { projectId: $projectId, contentId: $contentId }) {
        item { id }
      }
    }
    """
    data = graphql_request(query, {"projectId": project_id, "contentId": content_id})
    item_id = (
        data.get("data", {})
        .get("addProjectV2ItemById", {})
        .get("item", {})
        .get("id")
    )
    if not item_id:
        print("ERROR: Failed to add item to project", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Added item to project (Item ID: {item_id})")
    return item_id


def get_project_item_fields(project_id: str, item_id: str) -> list[dict[str, Any]]:
    """Return current single-select field values for a project item."""
    query = """
    query($projectId: ID!, $itemId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          item(id: $itemId) {
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
    }
    """
    data = graphql_request(query, {"projectId": project_id, "itemId": item_id})
    item = data.get("data", {}).get("node", {}).get("item")
    return (item or {}).get("fieldValues", {}).get("nodes", []) if item else []


def set_field_value(project_id: str, item_id: str, field_id: str, option_id: str) -> None:
    """Set a single-select field value on a project item."""
    query = """
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
    variables = {
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "value": {"singleSelectOptionId": option_id},
    }
    graphql_request(query, variables)


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    """Entry point."""
    repo_owner = os.environ.get("REPO_OWNER")
    repo_name = os.environ.get("REPO_NAME")
    issue_number = os.environ.get("ISSUE_NUMBER")
    issue_url = os.environ.get("ISSUE_URL")  # optional

    required = [repo_owner, repo_name, issue_number]
    if not all(required):
        print("ERROR: Missing required env vars REPO_OWNER, REPO_NAME, ISSUE_NUMBER", file=sys.stderr)
        sys.exit(1)

    # Preflight auth clarity (helps diagnose 401 quickly)
    graphql_whoami()
    print(f"Syncing issue/PR #{issue_number} from {repo_owner}/{repo_name}")
    if issue_url:
        print(f"URL: {issue_url}")
    print()

    # Resolve project, fields, and default options
    project_id = get_project_id()
    fields = get_project_fields(project_id)

    priority_field = fields["priority"]
    stage_field = fields["stage"]

    p2_option = next((o for o in priority_field.get("options", []) if o["name"] == "P2 (Normal)"), None)
    later_option = next((o for o in stage_field.get("options", []) if o["name"] == "Later"), None)

    if not p2_option:
        print("ERROR: Could not find 'P2 (Normal)' option in Priority field", file=sys.stderr)
        sys.exit(1)
    if not later_option:
        print("ERROR: Could not find 'Later' option in Stage field", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Found P2 (Normal) option (ID: {p2_option['id']})")
    print(f"✓ Found Later option (ID: {later_option['id']})")
    print()

    # Upsert item into project
    content_id = get_item_node_id(repo_owner, repo_name, issue_number)
    item_id = add_item_to_project(project_id, content_id)

    # Only set defaults if unset
    current_values = get_project_item_fields(project_id, item_id)
    priority_set = any((v.get("field") or {}).get("name") == "Priority" for v in current_values)
    stage_set = any((v.get("field") or {}).get("name") == "Stage" for v in current_values)

    if not priority_set:
        print("Setting Priority to P2 (Normal)…")
        set_field_value(project_id, item_id, priority_field["id"], p2_option["id"])
        print("✓ Priority set")
    else:
        print("✓ Priority already set, skipping")

    if not stage_set:
        print("Setting Stage to Later…")
        set_field_value(project_id, item_id, stage_field["id"], later_option["id"])
        print("✓ Stage set")
    else:
        print("✓ Stage already set, skipping")

    print("\n✅ Sync complete!")


if __name__ == "__main__":
    main()
