"""
Helper functions for formatting content for JIRA.
"""
import uuid

def create_summary_adf_document(summary, messages, channel_name):
    """
    Creates an Atlassian Document Format (ADF) document with an AI summary and the original thread link.

    Args:
        summary: AI-generated summary of the conversation
        messages: List of formatted messages from the thread
        channel_name: Name of the Slack channel

    Returns:
        ADF document structure
    """
    adf_doc = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Summary"}]
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": summary}]
            },
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Details"}]
            }
        ]
    }

    # Add messages with their content
    for msg in messages:
        message_text = msg.get("text", "")

        # If the message contains a curl command, format it
        original_text = message_text
        formatted_text = format_curl_command(message_text)

        # Check if formatting actually changed anything
        if formatted_text != original_text:
            # Split by "```" to extract code blocks
            parts = formatted_text.split("```")

            # Add user info and text before the curl command
            if parts[0].strip():
                adf_doc["content"].append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"{msg.get('username')}: {parts[0].strip()}"}]
                })
            else:
                adf_doc["content"].append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"{msg.get('username')}:"}]
                })

            # Process each curl code block
            for i in range(1, len(parts), 2):
                if i < len(parts):
                    # Add the code block
                    adf_doc["content"].append({
                        "type": "codeBlock",
                        "attrs": {"language": "bash"},
                        "content": [{"type": "text", "text": parts[i].strip()}]
                    })

                    # Add any text between code blocks
                    if i + 1 < len(parts) and parts[i + 1].strip():
                        adf_doc["content"].append({
                            "type": "paragraph",
                            "content": [{"type": "text", "text": parts[i + 1].strip()}]
                        })
        else:
            # Add as regular paragraph if no curl command was found
            adf_doc["content"].append({
                "type": "paragraph",
                "content": [{"type": "text", "text": f"{msg.get('username')}: {message_text}"}]
            })

    # Add file information if any
    file_info = []
    for msg in messages:
        if msg.get("files"):
            for file in msg.get("files", []):
                file_info.append(f"{file.get('name', 'unnamed file')} ({file.get('filetype', 'file')})")

    if file_info:
        adf_doc["content"].append({
            "type": "paragraph",
            "content": [{"type": "text", "text": f"Attachments: {', '.join(file_info)}"}]
        })

    # Add the original thread link
    thread_ts = next((msg.get("ts") for msg in messages if msg.get("is_parent")), messages[0].get("ts", ""))
    slack_thread_url = f"https://slack.com/archives/{channel_name}/p{thread_ts.replace('.', '')}"

    adf_doc["content"].append({
        "type": "paragraph",
        "content": [
            {"type": "text", "text": "Original thread: "},
            {
                "type": "text",
                "text": slack_thread_url,
                "marks": [{"type": "link", "attrs": {"href": slack_thread_url}}]
            }
        ]
    })

    return adf_doc
def format_curl_command(text):
    """
    Identifies and formats curl commands in a message text using an improved regex approach.

    Args:
        text: The message text that may contain curl commands

    Returns:
        Formatted text with curl commands properly formatted
    """
    import re

    # Quick check if curl is even in the text
    if "curl" not in text.lower():
        return text

    # More comprehensive regex pattern for curl commands
    # Captures curl and everything after it until a clear delimiter (double newline or end of string)
    curl_pattern = r'(curl(?:\s+-[a-zA-Z]+|\s+--[a-zA-Z\-]+|\s+"[^"]+"|\'[^\']+\'|\s+[^\s-][^\s]*)*(?:\s+https?://[^\s]+|\s+[^\s]+)(?:\s+-[a-zA-Z]+|\s+--[a-zA-Z\-]+|\s+\'[^\']+\'|\s+"[^"]+"|\s+[^\s-][^\s]*)*)'

    # Find all potential curl commands
    matches = re.finditer(curl_pattern, text, re.IGNORECASE | re.DOTALL)
    if not matches:
        return text

    # Track offsets to handle multiple replacements
    offset = 0
    formatted_text = text

    # Process each match
    for match in matches:
        curl_cmd = match.group(1)
        start_pos = match.start(1) + offset
        end_pos = match.end(1) + offset

        # Format the curl command with proper indentation and line breaks
        formatted_cmd = format_curl_parameters(curl_cmd)

        # Replace the original command with the formatted version in a code block
        replacement = f"```\n{formatted_cmd}\n```"
        formatted_text = formatted_text[:start_pos] + replacement + formatted_text[end_pos:]

        # Update offset for subsequent replacements
        offset += len(replacement) - (end_pos - start_pos)

    return formatted_text
def format_curl_parameters(curl_cmd):
    """
    Formats curl command parameters with line breaks and indentation.

    Args:
        curl_cmd: The curl command to format

    Returns:
        Formatted curl command with line breaks and indentation
    """
    import re

    # Pattern to find curl parameters
    param_pattern = r'(\s+)(-[a-zA-Z]|\s+--[a-zA-Z\-]+)'

    # Preserve the "curl" part at the beginning
    curl_parts = curl_cmd.split(' ', 1)
    curl_base = curl_parts[0]
    curl_rest = curl_parts[1] if len(curl_parts) > 1 else ""

    # Format parameters, preserving quotes and keeping URL intact
    formatted_params = re.sub(param_pattern, r'\n  \2', " " + curl_rest)

    # Handle URL parameter separately to keep it properly formatted
    url_match = re.search(r'(https?://[^\s"\']+|[^\s"\'-][^\s]*\.(?:com|org|net|io|gov)[^\s"\']*)', formatted_params)
    if url_match:
        url = url_match.group(1)
        # Ensure the URL is on its own line
        url_pos = formatted_params.find(url)
        if url_pos > 0 and formatted_params[url_pos - 1:url_pos] != "\n":
            formatted_params = formatted_params[:url_pos] + "\n  " + formatted_params[url_pos:]

    return curl_base + formatted_params


def create_adf_table(ticket_data, repo, version, table_identifier=None):
    """
    Converts ticket data into an Atlassian Document Format (ADF) table.
    
    Args:
        ticket_data: List of tickets to include in the table
        repo: Repository name
        version: Version tag
        table_identifier: Optional table identifier
        
    Returns:
        Tuple of (ADF document, table_identifier)
    """
    if table_identifier is None:
        table_identifier = str(uuid.uuid4())

    adf_table = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Promotion Status"}]
            },
            create_promotion_table(table_identifier, repo, version),
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Feature Details"}]
            },
            create_feature_table(ticket_data, str(uuid.uuid4()))
        ]
    }

    return adf_table, table_identifier

def create_feature_table(ticket_data, table_id):
    """
    Create a feature table in ADF format.
    
    Args:
        ticket_data: List of tickets to include
        table_id: Unique ID for the table
        
    Returns:
        ADF table object
    """
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

def create_promotion_table(table_id, repo, version):
    """
    Create a promotion status table in ADF format.
    
    Args:
        table_id: Unique ID for the table
        repo: Repository name
        version: Version tag
        
    Returns:
        ADF table object
    """
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