"""
Helper functions for interacting with the JIRA API.
"""
from io import BytesIO

import requests
import re
from bot.config.settings import (
    SOURCE_JIRA_URL, SOURCE_JIRA_USER, SOURCE_JIRA_API_TOKEN,
    SOURCE_JIRA_PROJECT_KEY, SOURCE_JIRA_ISSUE_URL,SLACK_BOT_TOKEN,
    JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT_KEY
)

def get_project_components(project_key, use_target_jira=False):
    """
    Fetches the components available for a JIRA project.

    Args:
        project_key: The JIRA project key
        use_target_jira: Whether to use target JIRA (for ticket creation) instead of source JIRA
        
    Returns:
        List of components with their IDs and names
    """
    try:
        # Choose which JIRA environment to use
        if use_target_jira:
            jira_url = JIRA_URL
            jira_user = JIRA_USER
            jira_api_token = JIRA_API_TOKEN
            print(f"Using target JIRA for components: {jira_url} with project {project_key}")
        else:
            jira_url = SOURCE_JIRA_URL
            jira_user = SOURCE_JIRA_USER
            jira_api_token = SOURCE_JIRA_API_TOKEN
            print(f"Using source JIRA for components: {jira_url} with project {project_key}")
            
        # For now, return mock data if credentials aren't available to simplify testing
        if not jira_url or not jira_user or not jira_api_token:
            print("Missing JIRA credentials - returning mock components")
            return [
                {"id": "10001", "name": "UI"},
                {"id": "10002", "name": "Backend"},
                {"id": "10003", "name": "API"},
                {"id": "10004", "name": "Database"},
                {"id": "10005", "name": "Documentation"}
            ]
        
        # Make JIRA API request
        url = f"{jira_url}/rest/api/3/project/{project_key}/components"
        print(f"Making request to: {url}")
        
        response = requests.get(url, auth=(jira_user, jira_api_token))
        if response.status_code == 200:
            components = response.json()
            print(f"Successfully retrieved {len(components)} components")
            return components
        else:
            print(f"Error fetching components: HTTP {response.status_code} - {response.text}")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching project components: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error fetching project components: {e}")
        return []  # Return empty list if there's an error

def extract_jira_tickets(project_key, text):
    """
    Extract JIRA ticket IDs from text.
    
    Args:
        project_key: JIRA project key to look for
        text: Text to search in
        
    Returns:
        List of JIRA ticket IDs found
    """
    pattern = rf"{project_key}-\d+"
    return re.findall(pattern, text)



def upload_files_to_jira(ticket_key, messages):
    """
    Uploads files from Slack messages to a JIRA ticket.

    Args:
        ticket_key (str): The key of the JIRA ticket (e.g., "PROJ-123").
        messages (list): List of message dictionaries, each possibly containing a "files" list.

    Returns:
        int: Number of successfully uploaded attachments.
    """
    successful_uploads = 0
    jira_upload_url = f"{JIRA_URL}/rest/api/3/issue/{ticket_key}/attachments"
    jira_headers = {
        "X-Atlassian-Token": "no-check"
    }

    for msg in messages:
        for file in msg.get("files", []):
            file_name = file.get("name", "attachment")
            file_url = file.get("url_private")
            mime_type = file.get("mimetype", "application/octet-stream")

            if not file_url:
                print(f"Skipping file with no URL: {file_name}")
                continue

            try:
                slack_headers = {
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
                }

                response = requests.get(file_url, headers=slack_headers)
                if response.status_code != 200:
                    print(f"Failed to download file {file_name}: {response.status_code}")
                    print("Response preview:", response.text[:300])
                    continue

                # Validate content-type
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type or "application/json" in content_type:
                    print(f"Unexpected content-type for {file_name}: {content_type}")
                    print("Response preview:", response.text[:300])
                    continue

                file_data = BytesIO(response.content)
                files = {
                    "file": (file_name, file_data, mime_type)
                }

                upload_response = requests.post(
                    jira_upload_url,
                    files=files,
                    auth=(JIRA_USER, JIRA_API_TOKEN),
                    headers=jira_headers
                )

                if upload_response.status_code in (200, 201):
                    successful_uploads += 1
                    print(f"Successfully uploaded: {file_name}")
                else:
                    print(f"Upload failed for {file_name}: {upload_response.status_code} - {upload_response.text}")

            except requests.RequestException as req_err:
                print(f"Request error for {file_name}: {req_err}")
            except Exception as e:
                print(f"Unexpected error for {file_name}: {e}")

    return successful_uploads


def get_jira_projects():
    """
    Returns a hardcoded list of target projects.

    Returns:
        List of projects with their keys and names
    """
    # Hardcoded list of target projects only
    projects = [
        {'key': 'NBP', 'name': 'NBP (demo:read from CP)', 'id': 'NBP'},
        {'key': 'CP', 'name': 'CP - CP', 'id': 'CP'},
        {'key': 'DEV', 'name': 'DEV - Development', 'id': 'DEV'},
        {'key': 'TEST', 'name': 'TEST - Testing', 'id': 'TEST'},
        {'key': 'HELP', 'name': 'HELP - Help Desk', 'id': 'HELP'}
    ]

    # Always include the default target project if it's not already in the list
    default_key = JIRA_PROJECT_KEY
    default_in_list = False

    for p in projects:
        if p['key'] == default_key:
            default_in_list = True
            break

    if not default_in_list and default_key:
        projects.append({
            'key': default_key,
            'name': f"{default_key} - Default Project",
            'id': default_key
        })

    return projects


def get_issue_comments(issue_key):
    """
    Fetches all comments for a specific JIRA issue.

    Args:
        issue_key: The JIRA issue key (e.g., 'NBP-123')

    Returns:
        List of comments with author, body, and creation date
    """
    if re.match(r'^NBP-\d+$', issue_key):
        return fetch_comments_based_on_project(issue_key,JIRA_URL,JIRA_API_TOKEN,JIRA_USER)
    else:
        return fetch_comments_based_on_project(issue_key, SOURCE_JIRA_URL, SOURCE_JIRA_API_TOKEN, SOURCE_JIRA_USER)

def fetch_comments_based_on_project(issue_key,jira_url,jira_token,jira_user):
    try:
        url = f"{jira_url}/rest/api/3/issue/{issue_key}/comment"

        response = requests.get(url, auth=(jira_user, jira_token))

        if response.status_code == 200:
            data = response.json()


            # add code here
            comments = data.get("comments", [])

            # Format comments in a consistent way
            formatted_comments = []
            for comment in comments:
                formatted_comments.append({
                    "author": comment.get("author", {}).get("displayName", "Unknown"),
                    "body": comment.get("body", ""),
                    "created": comment.get("created", "")
                })

            print(f"Successfully retrieved {len(formatted_comments)} comments for {issue_key}")
            return formatted_comments
        else:
            print(f"Error fetching comments for {issue_key}: HTTP {response.status_code} - {response.text}")
            return []

    except requests.exceptions.RequestException as e:
        print(f"Network error fetching comments for {issue_key}: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error fetching comments for {issue_key}: {e}")
        return []

def extract_comments_from_duplicates(duplicates):
    """
    Extract all comments from duplicate tickets by making JIRA API calls.

    Args:
        duplicates: List of dictionaries containing duplicate ticket information

    Returns:
        Dictionary mapping ticket keys to their comments
    """

    comments_by_ticket = {}

    for dup in duplicates:
        try:
            ticket_key = dup.get('issue_key', '')
            if not ticket_key:
                continue

            # Make a direct JIRA API call to get comments for this issue
            comments = get_issue_comments(ticket_key)

            # Only add to the result if we got comments
            if comments:
                comments_by_ticket[ticket_key] = comments

        except Exception as e:
            print(f"Error fetching comments for ticket {dup.get('key', 'unknown')}: {e}")

    return comments_by_ticket