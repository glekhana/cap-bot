"""
Handlers for release ticket operations.
"""
import re
import json
import requests
from slack_sdk import WebClient

from bot.config.settings import (
    SLACK_BOT_TOKEN, SOURCE_JIRA_URL, SOURCE_JIRA_USER, SOURCE_JIRA_API_TOKEN,
    SOURCE_JIRA_PROJECT_KEY, SOURCE_JIRA_ISSUE_URL, JIRA_URL, JIRA_USER,
    JIRA_API_TOKEN, JIRA_PROJECT_KEY, GITHUB_TOKEN, REPO_USER_NAME
)
from bot.utils.jira_formatters import create_adf_table
from bot.utils.jira_helpers import extract_jira_tickets

# Initialize Slack client
client = WebClient(token=SLACK_BOT_TOKEN)

# Headers for GitHub API
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def handle_submission_async(user_id, repo, tag1, tag2, channel_id, thread_ts, ticket_name, existing_ticket_id=None):
    """
    Handles the submission process, either creating a new ticket or appending to an existing one.
    
    Args:
        user_id: Slack user ID
        repo: Repository name
        tag1: Old tag
        tag2: New tag
        channel_id: Slack channel ID
        thread_ts: Slack thread timestamp
        ticket_name: Optional ticket name
        existing_ticket_id: Optional existing ticket ID to append to
    """
    try:
        # Fetch commits and PRs
        commits = get_commits_between_tags(repo, tag1, tag2)
        features = get_all_feature_details(repo, commits)

        jira_ticket = "NA"
        action_text = "created"

        if features:
            if existing_ticket_id:
                # Get ticket data but don't create a full table structure
                ticket_data = []
                for feature in features:
                    jira_ticket_url = f"{SOURCE_JIRA_ISSUE_URL}/{feature['Jira Ticket']}"

                    # Get JIRA ticket details
                    url = f"{SOURCE_JIRA_URL}/rest/api/2/issue/{feature['Jira Ticket']}"
                    response = requests.get(url, auth=(SOURCE_JIRA_USER, SOURCE_JIRA_API_TOKEN))

                    if response.status_code == 200:
                        issue_data = response.json()
                        assignee = issue_data.get("fields", {}).get("assignee", {})
                        assignee_id = assignee.get("accountId") if assignee else "Unassigned"
                        assignee_name = assignee.get("displayName") if assignee else "Unassigned"

                        ticket_data.append({
                            "key": feature["Jira Ticket"],
                            "summary": issue_data.get("fields", {}).get("summary", ""),
                            "assignee": {
                                "id": assignee_id,
                                "name": assignee_name
                            },
                            "jira_url": jira_ticket_url,
                            "PR": feature["PR"],
                            "tag": tag2
                        })

                # Append to existing ticket
                jira_ticket = append_to_jira_ticket(existing_ticket_id, ticket_data, tag2, repo)
                action_text = "updated"
            else:
                # Create new ticket
                ticket_data = get_jira_assignees(features, tag2, repo)
                jira_ticket = create_jira_release_ticket(ticket_data, tag2, repo, ticket_name)
        else:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="⚠️ No PRs found between tags."
            )
            return

        final_link = f"{SOURCE_JIRA_ISSUE_URL}/{jira_ticket}"

        # Send the final message to the same channel
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"🎉 Here's your {action_text} release ticket for *{repo}*:\n{final_link}"
        )
    except Exception as e:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"❌ Error generating release ticket: {str(e)}"
        )
        print(f"Error in handle_submission_async: {e}")

def get_commits_between_tags(repo, tag1, tag2):
    """
    Get commits between two tags.
    
    Args:
        repo: Repository name
        tag1: Old tag
        tag2: New tag
        
    Returns:
        List of commits
    """
    url = f"https://api.github.com/repos/{REPO_USER_NAME}/{repo}/compare/{tag1}...{tag2}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    commits = response.json().get("commits", [])
    
    # Filter out commits with "release", "poms", or "snapshot"
    filtered_commits = [
        commit for commit in commits
        if not re.search(r"release|poms|snapshot", commit["commit"]["message"], re.IGNORECASE)
    ]

    return filtered_commits

def get_all_feature_details(repo, commits):
    """
    Get feature details from commits.
    
    Args:
        repo: Repository name
        commits: List of commits
        
    Returns:
        List of features with PR and JIRA ticket info
    """
    features = []
    for commit in commits:
        sha = commit["sha"]
        url = f"https://api.github.com/repos/{REPO_USER_NAME}/{repo}/commits/{sha}/pulls"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            pr_data = response.json()
            for pr in pr_data:
                jira_tickets = extract_jira_tickets(SOURCE_JIRA_PROJECT_KEY, pr["body"])
                for jira in jira_tickets:
                    features.append({
                        "PR": pr["html_url"],
                        "PR #": pr["number"],
                        "Title": pr["title"],
                        "Jira Ticket": jira,
                        "Author": pr["user"]["login"]
                    })
    return features

def get_jira_assignees(features, version, repo):
    """
    Fetches assignees for a list of JIRA tickets.
    
    Args:
        features: List of features with JIRA ticket info
        version: Version tag
        repo: Repository name
        
    Returns:
        Tuple of (ADF table document, table identifier)
    """
    ticket_keys = [feature["Jira Ticket"] for feature in features]
    mapKeysAndPRs = {}
    mapKeysAndURLs = {}
    
    for feature in features:
        jira_ticket_url = f"{SOURCE_JIRA_ISSUE_URL}/{feature['Jira Ticket']}"
        mapKeysAndURLs.update({feature["Jira Ticket"]: jira_ticket_url})
        mapKeysAndPRs.update({feature["Jira Ticket"]: feature["PR"]})

    jql_query = f"key IN ({', '.join(ticket_keys)})"
    url = f"{SOURCE_JIRA_URL}/rest/api/2/search"

    params = {
        "jql": jql_query,
        "fields": ["key", "summary", "assignee"],
    }

    response = requests.get(url, auth=(SOURCE_JIRA_USER, SOURCE_JIRA_API_TOKEN), params=params)
    response.raise_for_status()

    issues = response.json().get("issues", [])
    ticket_data = [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "assignee": {
                "id":
                issue['fields']['assignee']['accountId']
                if issue["fields"]["assignee"] else "Unassigned",
                "name": issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else "Unassigned"
            },
            "jira_url": mapKeysAndURLs[issue["key"]],
            "PR": mapKeysAndPRs[issue["key"]],
            "tag": version
        }
        for issue in issues
    ]
    
    return create_adf_table(ticket_data, repo, version)

def create_jira_release_ticket(data, version, repo, ticket_name=None):
    """
    Creates a JIRA release ticket.
    
    Args:
        data: Tuple of (ADF document, table_identifier)
        version: Version tag
        repo: Repository name
        ticket_name: Optional ticket name
        
    Returns:
        JIRA ticket key
    """
    headers = {
        "Content-Type": "application/json",
    }
    
    url = f"{JIRA_URL}/rest/api/3/issue"
    if ticket_name is None:
        ticket_name = f"Release Notes for {repo} - {version}"

    # Extract just the ADF document from the tuple
    adf_document = data[0] if isinstance(data, tuple) else data

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": ticket_name,
            "description": adf_document,
            "issuetype": {"name": "Release"}
        }
    }

    response = requests.post(url, json=payload, auth=(JIRA_USER, JIRA_API_TOKEN), headers=headers)
    response.raise_for_status()

    return response.json().get("key")

def get_jira_ticket_content(ticket_id):
    """
    Fetches the content of an existing JIRA ticket.
    
    Args:
        ticket_id: JIRA ticket ID
        
    Returns:
        Tuple of (description, summary)
    """
    url = f"{SOURCE_JIRA_URL}/rest/api/3/issue/{ticket_id}"

    response = requests.get(url, auth=(SOURCE_JIRA_USER, SOURCE_JIRA_API_TOKEN))
    response.raise_for_status()

    issue_data = response.json()
    description = issue_data.get("fields", {}).get("description", {})

    return description, issue_data.get("fields", {}).get("summary", "")

def append_to_jira_ticket(ticket_id, ticket_data, version, repo):
    """
    Appends new data to an existing JIRA ticket.
    
    Args:
        ticket_id: Existing JIRA ticket ID
        ticket_data: List of ticket data to append
        version: Version tag
        repo: Repository name
        
    Returns:
        JIRA ticket ID
    """
    import uuid
    
    # Get existing ticket content
    existing_content, summary = get_jira_ticket_content(ticket_id)

    # Find existing tables in the content
    promotion_table_index = None
    feature_table_index = None

    for i, content_item in enumerate(existing_content.get("content", [])):
        if content_item.get("type") == "table":
            # Check if this is the promotion table (first table)
            if promotion_table_index is None:
                promotion_table_index = i
            # Check if this is the feature table (second table)
            elif feature_table_index is None:
                feature_table_index = i
                break

    # Create new rows for appending
    new_promotion_row = create_promotion_row(repo, version)
    new_feature_rows = create_feature_rows_for_append(ticket_data)

    # If both tables were found, update them
    if promotion_table_index is not None and feature_table_index is not None:
        # Add the new promotion row
        existing_content["content"][promotion_table_index]["content"].append(new_promotion_row)

        # Add all the new feature rows
        for feature_row in new_feature_rows:
            existing_content["content"][feature_table_index]["content"].append(feature_row)
    else:
        # If tables weren't found, create a new document structure
        print(f"Warning: Expected tables not found in ticket {ticket_id}. Creating new content.")

        # Create full new document structure with tables
        new_content = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Promotion Status"}]
                },
                create_promotion_table(str(uuid.uuid4()), repo, version),
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Feature Details"}]
                },
                create_feature_table(ticket_data, str(uuid.uuid4()))
            ]
        }

        existing_content = new_content

    # Update the ticket
    url = f"{SOURCE_JIRA_URL}/rest/api/3/issue/{ticket_id}"
    payload = {
        "fields": {
            "description": existing_content
        }
    }

    response = requests.put(url, json=payload, auth=(SOURCE_JIRA_USER, SOURCE_JIRA_API_TOKEN))
    response.raise_for_status()

    return ticket_id

def create_feature_rows_for_append(ticket_data):
    """
    Creates feature table rows for appending without creating a whole new table.
    
    Args:
        ticket_data: List of ticket data to format
        
    Returns:
        List of feature table rows in ADF format
    """
    import uuid

    feature_rows = []
    for row in ticket_data:
        feature_row = {
            "type": "tableRow",
            "content": [
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": row.get("jira_url", "#"),
                                    "marks": [
                                        {
                                            "type": "link",
                                            "attrs": {
                                                "href": row.get("jira_url")
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                    {"type": "text", "text": row["summary"]}]}]},
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": row["PR"],
                                    "marks": [
                                        {
                                            "type": "link",
                                            "attrs": {
                                                "href": row.get("PR", "#")
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": (
                                [
                                    {
                                        "type": "mention",
                                        "attrs": {
                                            "id": row["assignee"]["id"],
                                            "localId": "generated-uuid",
                                            "text": f"@{row['assignee']['name']}",
                                            "accessLevel": ""
                                        }
                                    },
                                    {"type": "text", "text": " "}
                                ]
                                if row["assignee"]
                                else [{"type": "text", "text": "Unassigned"}]
                            )
                        }
                    ]
                },
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "taskList",
                            "attrs": {
                                "localId": str(uuid.uuid4())
                            },
                            "content": [
                                {
                                    "type": "taskItem",
                                    "attrs": {
                                        "localId": str(uuid.uuid4()),
                                        "state": "TODO"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {"type": "tableCell", "attrs": {}, "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": ""
                            }
                        ]
                    }
                ]},
            ]
        }
        feature_rows.append(feature_row)

    return feature_rows

def create_promotion_row(repo, version):
    """
    Creates a single promotion table row for appending.
    
    Args:
        repo: Repository name
        version: Version tag
        
    Returns:
        ADF table row for promotion table
    """
    import uuid

    return {
        "type": "tableRow",
        "content": [
            {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": repo}]}]},
            {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": version}]}]},
            {
                "type": "tableCell",
                "attrs": {},
                "content": [
                    {
                        "type": "taskList",
                        "attrs": {
                            "localId": str(uuid.uuid4())
                        },
                        "content": [
                            {
                                "type": "taskItem",
                                "attrs": {
                                    "localId": str(uuid.uuid4()),
                                    "state": "TODO"
                                }
                            }
                        ]
                    }
                ]
            },
            {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": ""}]}]},
            {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": ""}]}]},
            {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": ""}]}]},
        ]
    }

def create_promotion_table(table_id, repo, version):
    """
    Creates a promotion table in ADF format.
    
    Args:
        table_id: Table identifier
        repo: Repository name
        version: Version tag
        
    Returns:
        ADF promotion table
    """
    import uuid
    
    return {
        "type": "table",
        "attrs": {
            "isNumberColumnEnabled": False,
            "layout": "default",
            "localId": table_id
        },
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph",
                                                                     "content": [{"type": "text",
                                                                                 "text": "Package"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Tag Cut"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Promoted?"}]}]},

                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Regression Link"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Promoted By"}]}]},
                    {
                        "type": "tableHeader",
                        "attrs": {},
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Promoted Date"
                                    }
                                ]
                            }
                        ]
                    },
                ]
            },
            {
                "type": "tableRow",
                "content": [
                    {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": repo}]}]},
                    {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": version}]}]},
                    {
                        "type": "tableCell",
                        "attrs": {},
                        "content": [
                            {
                                "type": "taskList",
                                "attrs": {
                                    "localId": str(uuid.uuid4())
                                },
                                "content": [
                                    {
                                        "type": "taskItem",
                                        "attrs": {
                                            "localId": str(uuid.uuid4()),
                                            "state": "TODO"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": "Regression Link"}]}]},
                    {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": "Promoted By"}]}]},
                    {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": "Promoted Date"}]}]}
                ]
            }
        ]
    }

def create_feature_table(ticket_data, table_id):
    """
    Creates a feature table in ADF format.
    
    Args:
        ticket_data: List of ticket data
        table_id: Table identifier
        
    Returns:
        ADF feature table
    """
    import uuid
    
    table = {
        "type": "table",
        "attrs": {
            "isNumberColumnEnabled": False,
            "layout": "default",
            "localId": table_id
        },
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph",
                                                                     "content": [{"type": "text",
                                                                                 "text": "Feature/Bug"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Summary"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "PR"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Owner"}]}]},
                    {"type": "tableHeader", "attrs": {}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Sign Off"}]}]},
                    {
                        "type": "tableHeader",
                        "attrs": {},
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Stage Verification Doc"
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ]
    }
    
    # Add rows for each ticket
    for row in ticket_data:
        table["content"].append({
            "type": "tableRow",
            "content": [
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": row.get("jira_url", "#"),
                                    "marks": [
                                        {
                                            "type": "link",
                                            "attrs": {
                                                "href": row.get("jira_url")
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [
                    {"type": "text", "text": row["summary"]}]}]},
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": row["PR"],
                                    "marks": [
                                        {
                                            "type": "link",
                                            "attrs": {
                                                "href": row.get("PR", "#")
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": (
                                [
                                    {
                                        "type": "mention",
                                        "attrs": {
                                            "id": row["assignee"]["id"],
                                            "localId": "generated-uuid",
                                            "text": f"@{row['assignee']['name']}",
                                            "accessLevel": ""
                                        }
                                    },
                                    {"type": "text", "text": " "}
                                ]
                                if row["assignee"]
                                else [{"type": "text", "text": "Unassigned"}]
                            )
                        }
                    ]
                },
                {
                    "type": "tableCell",
                    "attrs": {},
                    "content": [
                        {
                            "type": "taskList",
                            "attrs": {
                                "localId": str(uuid.uuid4())
                            },
                            "content": [
                                {
                                    "type": "taskItem",
                                    "attrs": {
                                        "localId": str(uuid.uuid4()),
                                        "state": "TODO"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {"type": "tableCell", "attrs": {}, "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": ""
                            }
                        ]
                    }
                ]},
            ]
        })
    
    return table 