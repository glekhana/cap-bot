"""
Handlers for JIRA ticket creation from Slack conversations.
"""
import json
from slack_sdk import WebClient
import requests
import re

from bot.config.settings import (
    SLACK_BOT_TOKEN, SOURCE_JIRA_PROJECT_KEY, SOURCE_JIRA_ISSUE_URL,
    JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_ISSUE_URL, JIRA_PROJECT_KEY
)
from bot.models.search import search_issues_via_proc
from bot.utils.slack_helpers import get_thread_messages
from bot.utils.jira_helpers import (
 upload_files_to_jira, get_jira_projects
)
from bot.utils.ai_helpers import (
    generate_from_thread_ticket_parameters, summarize_duplicate_issues
)
from bot.utils.jira_formatters import create_summary_adf_document

# Initialize Slack client
client = WebClient(token=SLACK_BOT_TOKEN)

def handle_thread_to_ticket_async(user_id, channel_id, message_ts, response_url):
    """
    Entry point for the thread-to-ticket flow.
    Sends immediate processing message and kicks off asynchronous processing.

    Args:
        user_id: Slack user ID
        channel_id: Slack channel ID
        message_ts: Slack message timestamp
        response_url: Slack response URL for sending updates
    """
    # Send immediate feedback to user
    client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text="🔄 Processing thread and checking for potential duplicates..."
    )

    # Start the duplicate check asynchronously
    check_duplicates_async(user_id, channel_id, message_ts, response_url)

def check_duplicates_async(user_id, channel_id, message_ts, response_url):
    """
    Asynchronously checks for duplicates and notifies user.

    Args:
        user_id: Slack user ID
        channel_id: Slack channel ID
        message_ts: Slack message timestamp
        response_url: Slack response URL for sending updates
    """
    try:
        # Get thread messages
        messages = get_thread_messages(client, channel_id, message_ts)

        if not messages:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text="❌ Couldn't retrieve messages from the thread."
            )
            return

        # Get channel info for context
        channel_info = client.conversations_info(channel=channel_id)
        channel_name = channel_info["channel"]["name"] if channel_info.get("ok") else "Unknown Channel"
        #TODO  exclude conversations from incentives bot
        # Generate only the title using AI
        # Format the conversation for the API
        conversation_text = ""
        for msg in messages:
            # Get user info
            user_info = client.users_info(user=msg.get("user", "unknown"))
            username = user_info["user"]["real_name"] if user_info.get("ok") else "Unknown User"

            # Skip messages from Incentives-Bot
            if "cap-bot" in username.lower() or "Cap Bot" in username.lower():
                continue

            # Also check if the message is from a bot with the name containing "incentives"
            if msg.get("bot_id") and msg.get("username") and "cap" in msg.get("username", "").lower():
                continue

            conversation_text = "\n".join(f"{msg.get('username', 'User')}: {msg.get('text', '')}")

        # Get title and suggested priority, but don't generate summary yet
        result = generate_from_thread_ticket_parameters(conversation_text)
        title = result['title']
        priority = result['priority']
        summary = result['summary']

        # Store context data for later use - don't generate summary yet
        ticket_context = {
            "user_id": user_id,
            "channel_id": channel_id,
            "message_ts": message_ts,
            "title": title,
            "priority": priority,
            "channel_name": channel_name,
            "messages": messages,
            "summary": summary,
            "conversation_text": conversation_text  # Store the conversation text for later summary generation
        }

        # Debug log
        print(f"check_duplicates_async - ticket_context keys: {ticket_context.keys()}")

        # Check for duplicate issues in the SOURCE JIRA using the raw thread content
        duplicates = search_issues_via_proc(summary)

        if duplicates:
            # Send immediate notification about duplicates
            duplicate_count = len(duplicates)

            duplicate_list = ""
            for i, dup in enumerate(duplicates[:5]):  # Show up to 5 duplicates
                if re.match(r'^NBP-\d+$', dup['issue_key']):
                    duplicate_list += f"• <{JIRA_ISSUE_URL}/{dup['issue_key']}|{dup['issue_key']}> - {dup['summary'][:80]}..\n"
                else:
                    duplicate_list += f"• <{SOURCE_JIRA_ISSUE_URL}/{dup['issue_key']}|{dup['issue_key']}> - {dup['summary'][:80]}...\n"
            analysis_message = (
                f"*🔍 Potential Similar Issues Found*\n\n"
                f"{duplicate_list}\n\n"
            )
            # Post permanent summary message about duplicates
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=analysis_message,
                unfurl_links=False  # Prevent JIRA links from expanding to save space
            )

            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"📋 Found {duplicate_count} potential duplicate issues in {SOURCE_JIRA_PROJECT_KEY}. Analyzing similarities..."
            )

            # Start the duplicate analysis asynchronously
            analyze_duplicates_async(duplicates, ticket_context)
        else:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"📋 Found 0 potential duplicate issues in {SOURCE_JIRA_PROJECT_KEY}. Please go ahead and create ticket"
            )
            actions_message = (
                f"_If you would like to create a ticket for this issue, click the button below:_"
            )
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=actions_message,
                blocks=[
                    {
                        "type": "actions",
                        "block_id": "ticket_creation_actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Create Ticket",
                                    "emoji": True
                                },
                                "style": "primary",
                                "value": json.dumps({"has_duplicates": True,
                                                     "title": title,
                                                     "summary": summary,
                                                     "priority": ticket_context["priority"]
                                                     #    ,
                                                     # "analysis":analysis,
                                                     # "suggested_solution":solution
                                                     }),
                                "action_id": "open_ticket_form"
                            }
                        ]
                    }
                ]
            )



    except Exception as e:
        print(f"Error checking duplicates: {e}")
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=f"❌ Error processing thread: {str(e)}"
        )

def analyze_duplicates_async(duplicates, ticket_context):
    """
    Asynchronously analyzes duplicates and asks for user confirmation.

    Args:
        duplicates: List of potential duplicate tickets
        ticket_context: Dictionary with ticket creation context
    """
    try:
        # Extract necessary context
        title = ticket_context["title"]
        channel_id = ticket_context["channel_id"]
        message_ts = ticket_context["message_ts"]
        conversation_text = ticket_context["conversation_text"]
        summary = ticket_context["summary"]

        # Generate AI analysis of potential duplicates
        duplicate_analysis = summarize_duplicate_issues(title, summary, conversation_text, duplicates)

        # Format duplicate list for display in Slack - keep this part as is
        duplicate_list = ""
        for i, dup in enumerate(duplicates[:5]):  # Show up to 5 duplicates
            if re.match(r'^NBP-\d+$', dup['issue_key']):
                duplicate_list += f"• <{JIRA_ISSUE_URL}/{dup['issue_key']}|{dup['issue_key']}> - {dup['summary'][:80]}...- {dup['combined_score']}...\n"
            else:
                duplicate_list += f"• <{SOURCE_JIRA_ISSUE_URL}/{dup['issue_key']}|{dup['issue_key']}> - {dup['summary'][:80]}..- {dup['combined_score']}.\n"

        if len(duplicates) > 5:
            duplicate_list += f"_...and {len(duplicates) - 5} more potential matches_\n"

        # Store duplicates in context
        ticket_context["duplicates"] = duplicates
        ticket_context["duplicate_analysis"] = duplicate_analysis

        # Ensure channel_id and message_ts are explicitly set in ticket_context
        if "channel_id" not in ticket_context and channel_id:
            ticket_context["channel_id"] = channel_id

        if "message_ts" not in ticket_context and message_ts:
            ticket_context["message_ts"] = message_ts

        # Extract RCA and solution from the structured response
        analysis = duplicate_analysis.get("analysis", "Unable to determine root cause.")
        solution = duplicate_analysis.get("suggested_solution", "No suggested solution available.")
        
        # Format the message with better visual structure and organization
        analysis_message = (
            f"*📋 Analysis Based on Similar Issues*\n\n"
            f"*Analysis:*\n"
            f"{analysis}\n\n"
            f"*Potential Solution:*\n"
            f"{solution}\n\n"
            f"_If you believe this is a new issue, please continue with ticket creation._"
        )

        # Post permanent summary message about duplicates
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=analysis_message,
            unfurl_links=False  # Prevent JIRA links from expanding to save space
        )
        actions_message = (
            f"_If you would like to create a ticket for this issue, click the button below:_"
        )

        # Add a button that users can click to open the ticket creation form
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=actions_message,
            blocks=[
                {
                    "type": "actions",
                    "block_id": "ticket_creation_actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Create Ticket",
                                "emoji": True
                            },
                            "style": "primary",
                            "value": json.dumps({"has_duplicates": True,
                                                 "title":title,
                                                 "summary":summary,
                                                 "priority":ticket_context["priority"]
                                                 #    ,
                                                 # "analysis":analysis,
                                                 # "suggested_solution":solution
                                                 }),
                            "action_id": "open_ticket_form"
                        }
                    ]
                }
            ]
        )


    except Exception as e:
        print(f"Error in duplicate analysis: {e}")
        client.chat_postMessage(
            channel=ticket_context["channel_id"],
            thread_ts=ticket_context["message_ts"],
            text=f"❌ Error analyzing duplicates: {str(e)}"
        )


def show_ticket_creation_form(ticket_context, has_duplicates=False):
    """
    Open a modal dialog for ticket creation with appropriate options.

    Args:
        ticket_context: Dictionary with ticket creation context
        has_duplicates: Whether potential duplicates were found
    """
    try:
        # Make sure we have the required trigger_id
        trigger_id = ticket_context.get("trigger_id")
        if not trigger_id:
            raise ValueError("Missing trigger_id required to open modal")

        channel_id = ticket_context["channel_id"]
        message_ts = ticket_context["message_ts"]
        title = ticket_context["title"]
        priority = ticket_context.get("priority", "Medium")
        summary = ticket_context.get("summary", "")  # Get summary if available

        # Create comprehensive context
        form_context = {
            "channel_id": channel_id,
            "message_ts": message_ts,
            "title": title,
            "priority": priority,
            "summary": summary,
            "conversation_text": ticket_context.get("conversation_text", "")
        }

        # Include duplicate analysis if available
        if "duplicate_analysis" in ticket_context and isinstance(ticket_context["duplicate_analysis"], dict):
            form_context["duplicate_analysis"] = {
                "rca": ticket_context["duplicate_analysis"].get("rca", ""),
                "suggested_solution": ticket_context["duplicate_analysis"].get("suggested_solution", "")
            }

        # JSON serialization
        try:
            private_metadata = json.dumps(form_context, default=lambda o: list(o) if isinstance(o, set) else str(o))
        except TypeError:
            private_metadata = json.dumps({
                "channel_id": channel_id,
                "message_ts": message_ts,
                "title": title,
                "priority": priority,
                "summary": summary
            })

        # Get available target projects with value length validation
        projects = get_jira_projects()
        project_options = []

        for project in projects:
            # Ensure project key is not too long (Slack has a 150 char limit)
            project_key = project.get('key', '')
            if len(project_key) > 75:  # Keep well under the limit
                project_key = project_key[:75]  # Truncate if too long

            project_options.append({
                "text": {
                    "type": "plain_text",
                    "text": project.get('name', '')[:75]  # Also limit text length
                },
                "value": project_key
            })

        # Default project (use NBP as default)
        default_project = None
        for option in project_options:
            if option["value"] == "NBP":
                default_project = option
                break

        # If default not found, use first option
        if not default_project and project_options:
            default_project = project_options[0]

        # Component options
        component_options = [
            {"text": {"type": "plain_text", "text": "UI"}, "value": "UI"},
            {"text": {"type": "plain_text", "text": "Backend"}, "value": "Backend"},
            {"text": {"type": "plain_text", "text": "API"}, "value": "API"},
            {"text": {"type": "plain_text", "text": "Database"}, "value": "Database"},
            {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"}
        ]

        # Ensure priority is one of the allowed values
        valid_priorities = ["Highest", "High", "Medium", "Low", "Lowest"]
        if priority not in valid_priorities:
            priority = "Medium"  # Default if invalid

        # Create modal view
        view = {
            "type": "modal",
            "callback_id": "ticket_creation_modal",
            "private_metadata": private_metadata,
            "title": {
                "type": "plain_text",
                "text": "Create JIRA Ticket"
            },
            "submit": {
                "type": "plain_text",
                "text": "Create Ticket"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Create a JIRA ticket from this thread*" +
                                (
                                    "\n\n⚠️ *Potential duplicates have been found.* Please review the duplicates summary in the thread before creating a ticket." if has_duplicates else "")
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "input",
                    "block_id": "title_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Title"
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "title_input",
                        "initial_value": title,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter a title for the ticket"
                        }
                    }
                },
                {
                    "type": "input",
                    "block_id": "summary_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Summary"
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "summary_input",
                        "initial_value": summary,
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter a detailed summary of the issue"
                        }
                    }
                },
                {
                    "type": "input",
                    "block_id": "project_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Project"
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "project_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a project"
                        },
                        "options": project_options,
                        "initial_option": default_project
                    } if default_project else {
                        "type": "static_select",
                        "action_id": "project_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a project"
                        },
                        "options": project_options
                    }
                },
                {
                    "type": "input",
                    "block_id": "priority_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Priority"
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "priority_select",
                        "initial_option": {
                            "text": {
                                "type": "plain_text",
                                "text": priority
                            },
                            "value": priority
                        },
                        "options": [
                            {"text": {"type": "plain_text", "text": "Highest"}, "value": "Highest"},
                            {"text": {"type": "plain_text", "text": "High"}, "value": "High"},
                            {"text": {"type": "plain_text", "text": "Medium"}, "value": "Medium"},
                            {"text": {"type": "plain_text", "text": "Low"}, "value": "Low"},
                            {"text": {"type": "plain_text", "text": "Lowest"}, "value": "Lowest"}
                        ]
                    }
                },
                {
                    "type": "input",
                    "block_id": "labels_block",
                    "optional": True,
                    "label": {
                        "type": "plain_text",
                        "text": "Labels (comma separated)"
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "labels_input",
                        "initial_value": "incentives_product_bug",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "E.g., bug,ui,backend"
                        }
                    }
                },
                {
                    "type": "input",
                    "block_id": "component_block",
                    "optional": True,
                    "label": {
                        "type": "plain_text",
                        "text": "Component"
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "component_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a component"
                        },
                        "options": component_options
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "The ticket will be created using the information above. Additional details from the Slack thread will be included automatically."
                        }
                    ]
                }
            ]
        }

        # Open the modal with the trigger_id
        client.views_open(
            trigger_id=trigger_id,
            view=view
        )

    except Exception as e:
        print(f"Error showing ticket creation form: {e}")
        import traceback
        traceback.print_exc()

        # Notify in the thread
        try:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"❌ Error opening ticket form: {str(e)}"
            )
        except:
            pass

def create_jira_ticket(ticket_context, user_id):
    """
    Create a JIRA ticket with the provided information.
    
    Args:
        ticket_context: Dictionary with ticket creation context
        user_id: ID of the user who initiated the ticket creation
        
    Returns:
        Dictionary with created ticket information or error details
    """
    try:
        # Extract necessary context
        channel_id = ticket_context.get("channel_id")
        message_ts = ticket_context.get("message_ts")
        title = ticket_context.get("title", "")
        summary = ticket_context.get("summary", "")
        project = ticket_context.get("project", JIRA_PROJECT_KEY)
        priority = ticket_context.get("priority", "Medium")
        labels = ticket_context.get("labels", [])
        component = ticket_context.get("component")
        conversation_text = ticket_context.get("conversation_text", "")
        # thread_ts = next((msg.get("ts") for msg in messages if msg.get("is_parent")), messages[0].get("ts", ""))
        # slack_thread_url = f"https://slack.com/archives/{channel_name}/p{thread_ts.replace('.', '')}"

        # Format the description with context about the Slack conversation
        description = f"*Created from Slack Conversation*\n\n"
        description += f"*Summary:*\n{summary}\n\n"
        description += f"*Conversation:*\n{conversation_text}\n\n"
        
        # If we have duplicate analysis, include it
        if "duplicate_analysis" in ticket_context:
            duplicate_analysis = ticket_context["duplicate_analysis"]
            if isinstance(duplicate_analysis, dict):
                rca = duplicate_analysis.get("rca", "")
                solution = duplicate_analysis.get("suggested_solution", "")
                
                if rca:
                    description += f"*Root Cause Analysis:*\n{rca}\n\n"
                if solution:
                    description += f"*Suggested Solution:*\n{solution}\n\n"
        
        # Create the issue data
        issue_data = {
            "fields": {
                "project": {
                    "key": project
                },
                "summary": title,
                "description": description,
                "issuetype": {
                    "name": "Bug"  # Default to Bug type
                },
                "priority": {
                    "name": priority
                }
            }
        }
        
        # Add labels if any
        if labels:
            issue_data["fields"]["labels"] = labels if isinstance(labels, list) else [l.strip() for l in labels.split(",")]
        
        # Add component if specified
        if component:
            issue_data["fields"]["components"] = [{"id": component}]
        
        # Make the JIRA API call
        response = requests.post(
            f"{JIRA_URL}/rest/api/2/issue",
            json=issue_data,
            auth=(JIRA_USER, JIRA_API_TOKEN),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code in (200, 201):
            result = response.json()
            issue_key = result.get("key", "")
            issue_id = result.get("id", "")
            issue_url = f"{JIRA_URL}/browse/{issue_key}"
            
            # Return success with issue details
            return {
                "success": True,
                "issue_key": issue_key,
                "issue_id": issue_id,
                "issue_url": issue_url,
                "message": f"JIRA ticket {issue_key} created successfully."
            }
        else:
            error_msg = f"JIRA API error: {response.status_code} - {response.text}"
            print(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    except Exception as e:
        error_msg = f"Error creating JIRA ticket: {str(e)}"
        print(error_msg)
        return {
            "success": False,
            "error": error_msg
        }


