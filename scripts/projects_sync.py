@@
-    query = """
-    query($projectId: ID!, $itemId: ID!) {
-      node(id: $projectId) {
-        ... on ProjectV2 {
-          item(id: $itemId) {
-            id
-            fieldValues(first: 50) {
-              nodes {
-                __typename
-                ... on ProjectV2ItemFieldSingleSelectValue {
-                  field {
-                    __typename
-                    ... on ProjectV2SingleSelectField { id name }
-                  }
-                  optionId
-                  name
-                }
-              }
-            }
-          }
-        }
-      }
-    }
-    """
+    query = """
+    query($projectId: ID!, $itemId: ID!) {
+      node(id: $projectId) {
+        ... on ProjectV2 {
+          item(id: $itemId) {
+            id
+            fieldValues(first: 50) {
+              nodes {
+                __typename
+                ... on ProjectV2ItemFieldSingleSelectValue  { field { id name } optionId name }
+                ... on ProjectV2ItemFieldDateValue          { field { id name } value }
+                ... on ProjectV2ItemFieldTextValue          { field { id name } text }
+                ... on ProjectV2ItemFieldNumberValue        { field { id name } number }
+                ... on ProjectV2ItemFieldRepositoryValue    { field { id name } repository { nameWithOwner } }
+                ... on ProjectV2ItemFieldTitleValue         { field { id name } title }
+                ... on ProjectV2ItemFieldAssigneesValue     { field { id name } assignees(first: 10) { nodes { login } } }
+                ... on ProjectV2ItemFieldLabelValue         { field { id name } labels(first: 10) { nodes { name } } }
+                ... on ProjectV2ItemFieldMilestoneValue     { field { id name } milestone { title } }
+                ... on ProjectV2ItemFieldTrackedByValue     { field { id name } createdAt }
+                ... on ProjectV2ItemFieldPullRequestValue   { field { id name } pullRequests(first: 10) { nodes { number title } } }
+              }
+            }
+          }
+        }
+      }
+    }
+    """
