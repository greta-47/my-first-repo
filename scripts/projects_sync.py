#!/usr/bin/env python3
"""
Sync issues and pull requests to GitHub Project V2.

This script:
1. Resolves the Project ID from owner+number via GraphQL
2. Finds field IDs for Priority and Stage using inline fragments
3. Upserts the current Issue/PR into the Project
4. Sets default values: Priority=P2 (Normal), Stage=Later (if unset)
5. Idempotent and logs only IDs/URLs (no sensitive data)
"""

import json
import os
import sys
from typing import Any

import requests


def graphql_request(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL request against GitHub API."""
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("ERROR: GH_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
        sys.exit(1)

    return data


def get_project_id(owner: str, number: str) -> str:
    """Get the Project V2 ID from owner and project number."""
    query = """
    query($owner: String!, $number: Int!) {
      user(login: $owner) {
        projectV2(number: $number) {
          id
          title
        }
      }
    }
    """

    data = graphql_request(query, {"owner": owner, "number": int(number)})

    project = data.get("data", {}).get("user", {}).get("projectV2")
    if not project:
        print(f"ERROR: Could not find project #{number} for user {owner}", file=sys.stderr)
        sys.exit(1)

    project_id = project["id"]
    project_title = project["title"]
    print(f"✓ Found project: {project_title} (ID: {project_id})")
    return project_id


def get_project_fields(project_id: str) -> dict[str, Any]:
    """Get field IDs and options for Priority and Stage fields."""
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 50) {
            nodes {
              __typename
              ... on ProjectV2Field {
                id
                name
              }
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
              ... on ProjectV2IterationField {
                id
                name
              }
            }
          }
        }
      }
    }
    """

    data = graphql_request(query, {"projectId": project_id})
    fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])

    priority_field = None
    stage_field = None

    for field in fields:
        if (
            field.get("name") == "Priority"
            and field.get("__typename") == "ProjectV2SingleSelectField"
        ):
            priority_field = field
        elif (
            field.get("name") == "Stage" and field.get("__typename") == "ProjectV2SingleSelectField"
        ):
            stage_field = field

    if not priority_field:
        print("ERROR: Could not find Priority field in project", file=sys.stderr)
        sys.exit(1)

    if not stage_field:
        print("ERROR: Could not find Stage field in project", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Found Priority field (ID: {priority_field['id']})")
    print(f"✓ Found Stage field (ID: {stage_field['id']})")

    return {
        "priority": priority_field,
        "stage": stage_field,
    }


def get_item_node_id(repo_owner: str, repo_name: str, issue_number: str) -> str:
    """Get the node ID for an issue or pull request."""
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        issueOrPullRequest(number: $number) {
          ... on Issue {
            id
          }
          ... on PullRequest {
            id
          }
        }
      }
    }
    """

    data = graphql_request(
        query,
        {"owner": repo_owner, "name": repo_name, "number": int(issue_number)},
    )

    item = data.get("data", {}).get("repository", {}).get("issueOrPullRequest")
    if not item or "id" not in item:
        print(f"ERROR: Could not find issue/PR #{issue_number}", file=sys.stderr)
        sys.exit(1)

    node_id = item["id"]
    print(f"✓ Found issue/PR #{issue_number} (ID: {node_id})")
    return node_id


def add_item_to_project(project_id: str, content_id: str) -> str:
    """Add an issue/PR to the project. Returns the project item ID."""
    query = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
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


def get_project_item_fields(project_id: str, item_id: str) -> dict[str, Any]:
    """Get current field values for a project item."""
    query = """
    query($projectId: ID!, $itemId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          item(id: $itemId) {
            id
            fieldValues(first: 50) {
              nodes {
                ... on ProjectV2ItemFieldSingleSelectValue {
                  field {
                    ... on ProjectV2SingleSelectField {
                      id
                      name
                    }
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

    try:
        data = graphql_request(query, {"projectId": project_id, "itemId": item_id})
        item = data.get("data", {}).get("node", {}).get("item")
        if item:
            return item.get("fieldValues", {}).get("nodes", [])
    except Exception:
        pass

    return []


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
        projectV2Item {
          id
        }
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


def main() -> None:
    """Main entry point."""
    project_owner = os.environ.get("PROJECT_OWNER")
    project_number = os.environ.get("PROJECT_NUMBER")
    repo_owner = os.environ.get("REPO_OWNER")
    repo_name = os.environ.get("REPO_NAME")
    issue_number = os.environ.get("ISSUE_NUMBER")
    issue_url = os.environ.get("ISSUE_URL")

    if not all([project_owner, project_number, repo_owner, repo_name, issue_number]):
        print("ERROR: Missing required environment variables", file=sys.stderr)
        print(
            "Required: PROJECT_OWNER, PROJECT_NUMBER, REPO_OWNER, REPO_NAME, ISSUE_NUMBER",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Syncing issue/PR #{issue_number} to project {project_owner}/{project_number}")
    print(f"URL: {issue_url}")
    print()

    project_id = get_project_id(project_owner, project_number)
    fields = get_project_fields(project_id)

    priority_field = fields["priority"]
    stage_field = fields["stage"]

    p2_option = next(
        (opt for opt in priority_field["options"] if opt["name"] == "P2 (Normal)"),
        None,
    )
    later_option = next(
        (opt for opt in stage_field["options"] if opt["name"] == "Later"),
        None,
    )

    if not p2_option:
        print("ERROR: Could not find 'P2 (Normal)' option in Priority field", file=sys.stderr)
        sys.exit(1)

    if not later_option:
        print("ERROR: Could not find 'Later' option in Stage field", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Found P2 (Normal) option (ID: {p2_option['id']})")
    print(f"✓ Found Later option (ID: {later_option['id']})")
    print()

    content_id = get_item_node_id(repo_owner, repo_name, issue_number)

    try:
        item_id = add_item_to_project(project_id, content_id)
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Item already in project, skipping add")
            print()
        else:
            raise

    current_values = get_project_item_fields(project_id, item_id)

    priority_set = any(val.get("field", {}).get("name") == "Priority" for val in current_values)
    stage_set = any(val.get("field", {}).get("name") == "Stage" for val in current_values)

    if not priority_set:
        print("Setting Priority to P2 (Normal)...")
        set_field_value(project_id, item_id, priority_field["id"], p2_option["id"])
        print("✓ Priority set")
    else:
        print("✓ Priority already set, skipping")

    if not stage_set:
        print("Setting Stage to Later...")
        set_field_value(project_id, item_id, stage_field["id"], later_option["id"])
        print("✓ Stage set")
    else:
        print("✓ Stage already set, skipping")

    print()
    print("✅ Sync complete!")


if __name__ == "__main__":
    main()
