#!/usr/bin/env python3
"""
Sync issues and pull requests to GitHub Project V2.

This script:
1. Resolves the Project ID (prefers env PROJECT_ID; falls back to owner+number via GraphQL)
2. Finds field IDs for Priority and Status using inline fragments
3. Upserts the current Issue/PR into the Project
4. Sets default values: Priority=P2 (Normal), Status=Todo/Backlog (only if unset)
5. Idempotent and logs only IDs/URLs (no sensitive data)
"""

import json
import os
import sys
from typing import Any

import requests  # type: ignore[import-untyped]


# -----------------------------
# Helpers
# -----------------------------
def graphql_request(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL request against the GitHub API."""
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("ERROR: GH_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data and data["errors"]:
        # Print diagnostics but keep it minimal (no secrets)
        print("GraphQL errors:", file=sys.stderr)
        print(json.dumps(data["errors"], indent=2), file=sys.stderr)
        sys.exit(1)

    return data


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
    """Fetch field configs (Priority, Status) using inline fragments.
    This avoids union selection errors on ProjectV2 field types."""
    query = """
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

    data = graphql_request(query, {"projectId": project_id})
    fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", []) or []

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
    data = graphql_request(
        query,
        {"owner": repo_owner, "name": repo_name, "number": int(issue_number)},
    )
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
    item_id = data.get("data", {}).get("addProjectV2ItemById", {}).get("item", {}).get("id")
    if not item_id:
        print("ERROR: Failed to add item to project", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Added item to project (Item ID: {item_id})")
    return item_id


def get_project_item_fields(project_id: str, item_id: str) -> list[dict[str, Any]]:
    """Return current single-select field values for a project item."""
    query = """
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
    data = graphql_request(query, {"itemId": item_id})
    item = data.get("data", {}).get("node")
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
        print(
            "ERROR: Missing required env vars REPO_OWNER, REPO_NAME, ISSUE_NUMBER",
            file=sys.stderr,
        )
        sys.exit(1)
    repo_owner = repo_owner or ""
    repo_name = repo_name or ""
    issue_number = issue_number or ""

    print(f"Syncing issue/PR #{issue_number} from {repo_owner}/{repo_name}")
    if issue_url:
        print(f"URL: {issue_url}")
    print()

    # Resolve project, fields, and default options
    project_id = get_project_id()
    fields = get_project_fields(project_id)

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

    # Upsert item into project
    content_id = get_item_node_id(repo_owner, repo_name, issue_number)
    item_id = add_item_to_project(project_id, content_id)

    # Only set defaults if unset
    current_values = get_project_item_fields(project_id, item_id)
    priority_set = any((v.get("field") or {}).get("name") == "Priority" for v in current_values)
    status_set = any((v.get("field") or {}).get("name") == "Status" for v in current_values)

    if priority_field and p2_option and not priority_set:
        print("Setting Priority to P2 (Normal)…")
        set_field_value(project_id, item_id, priority_field["id"], p2_option["id"])
        print("✓ Priority set")
    elif priority_set:
        print("✓ Priority already set, skipping")
    elif not priority_field:
        print("⊘ Priority field not found, skipping")
    elif not p2_option:
        print("⊘ Priority option not found, skipping")

    if status_field and status_option and not status_set:
        print(f"Setting Status to {status_option['name']}…")
        set_field_value(project_id, item_id, status_field["id"], status_option["id"])
        print("✓ Status set")
    elif status_set:
        print("✓ Status already set, skipping")
    elif not status_field:
        print("⊘ Status field not found, skipping")
    elif not status_option:
        print("⊘ Status option not found, skipping")

    print("\n✅ Sync complete!")


if __name__ == "__main__":
    main()
