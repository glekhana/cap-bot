
import json
import threading

import requests
from bot.handlers.ticket_handlers import create_jira_ticket
from bot.utils.jira_formatters import create_summary_adf_document
from bot.utils.jira_helpers import extract_jira_tickets, upload_files_to_jira
from bot.utils.slack_helpers import get_full_thread_messages
from bot.config.settings import (
    SLACK_BOT_TOKEN, SOURCE_JIRA_PROJECT_KEY, SOURCE_JIRA_ISSUE_URL,
    JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_ISSUE_URL, JIRA_PROJECT_KEY
)

def handle_ticket_modal_submission(ack, body, view, client):
    """
    Handle the submission of the ticket creation modal.
    
    Args:
        ack: Acknowledgement function
        body: Request body
        view: View data
        client: Slack client
    """
    # Acknowledge the submission
    ack()
    
    try:
        # Extract values from the modal
        values = view["state"]["values"]
        
        # Get title from input
        title = values["title_block"]["title_input"]["value"]
        
        # Get project from select
        project_value = values["project_block"]["project_select"]["selected_option"]["value"]
        
        # Get priority from select
        priority_value = values["priority_block"]["priority_select"]["selected_option"]["value"]
        
        # Get labels from input (optional)
        labels_value = values.get("labels_block", {}).get("labels_input", {}).get("value", "")
        
        # Get component from select (optional)
        component_value = None
        component_block = values.get("component_block", {}).get("component_select", {})
        if "selected_option" in component_block:
            component_value = component_block["selected_option"]["value"]
        
        # Get the original ticket context from private_metadata
        ticket_context = json.loads(view["private_metadata"])
        
        # Update ticket context with form values
        ticket_context["title"] = title
        ticket_context["project"] = project_value
        ticket_context["priority"] = priority_value
        ticket_context["labels"] = labels_value.split(",") if labels_value else []
        if component_value:
            ticket_context["component"] = component_value
        
        # Get the user who submitted the form
        user_id = body["user"]["id"]
        
        # Create the ticket
        create_jira_ticket(ticket_context, user_id)
        
    except Exception as e:
        print(f"Error processing ticket creation modal: {e}")
        
        # Notify the user of the error in a DM
        try:
            user_id = body["user"]["id"]
            client.chat_postMessage(
                channel=user_id,
                text=f"❌ Error creating ticket: {str(e)}"
            )
        except Exception as dm_error:
            print(f"Error sending DM about ticket creation failure: {dm_error}")

def create_thread_to_ticket_async(client,user_id, channel_id, message_ts, response_url,ticket_context):
        """
        Asynchronously processes the thread and creates a JIRA ticket with AI summary.

        Args:
            user_id: The ID of the user who triggered the shortcut
            channel_id: The ID of the channel containing the thread
            message_ts: The timestamp of the message
            response_url: URL for sending messages back to Slack
        """
        try:
            # Get all messages in the thread
            messages = get_full_thread_messages(client, channel_id, message_ts)

            if not messages:
                # Reply in the thread with an error message
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text="Couldn't retrieve messages from the thread."
                )
                return

            # Get channel info for context
            channel_info = client.conversations_info(channel=channel_id)
            channel_name = channel_info["channel"]["name"] if channel_info.get("ok") else "Unknown Channel"

            title  =ticket_context['title']
            priority = ticket_context['priority']
            labels =  ticket_context['labels']
            components = ticket_context['component']
            # Create the ADF document for the JIRA description
            adf_doc = create_summary_adf_document(ticket_context['summary'], messages, channel_name)

            # Create the JIRA ticket
            url = f"{JIRA_URL}/rest/api/3/issue"
            payload = {
                "fields": {
                    "project": {"key": JIRA_PROJECT_KEY},
                    "summary": title,
                    "description": adf_doc,
                    "priority": {"name": priority},
                    "labels": labels,
                  #  "components":[{"name": components}],
                    "issuetype": {"name": "Bug"},
                    "customfield_10039":message_ts,
                    "customfield_10038":channel_id
                }
            }

            # Extract JIRA tickets mentioned in the thread to link them
            all_text = " ".join([msg.get("text", "") for msg in messages])
            mentioned_tickets = extract_jira_tickets(JIRA_PROJECT_KEY, all_text)

            response = requests.post(url, json=payload, auth=(JIRA_USER, JIRA_API_TOKEN))
            response.raise_for_status()

            new_ticket_key = response.json().get("key")

            # Link to any mentioned JIRA tickets
            if mentioned_tickets and new_ticket_key:
                link_jira_tickets(new_ticket_key, mentioned_tickets)

            # Upload all files to JIRA
            attachments_uploaded = upload_files_to_jira(new_ticket_key, messages)

            # Send a message with the JIRA ticket link
            attachment_msg = f" with {attachments_uploaded} attachment(s)" if attachments_uploaded > 0 else ""

            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"📝 Created JIRA ticket from thread{attachment_msg}: <{JIRA_ISSUE_URL}/{new_ticket_key}|{new_ticket_key}>"
            )


        except Exception as e:
            print(f"Error creating ticket from thread: {e}")
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"❌ Error creating JIRA ticket: {str(e)}"
            )
def link_jira_tickets(source_ticket, target_tickets):
    """
    Creates links between JIRA tickets.

    Args:
        source_ticket: Key of the source ticket
        target_tickets: List of keys for tickets to link to
    """
    for target in target_tickets:
        try:
            # Create a "relates to" link between tickets
            url = f"{JIRA_URL}/rest/api/3/issueLink"
            payload = {
                "outwardIssue": {"key": source_ticket},
                "inwardIssue": {"key": target},
                "type": {"name": "Relates"}
            }

            response = requests.post(url, json=payload, auth=(JIRA_USER, JIRA_API_TOKEN))

            if response.status_code not in (200, 201, 204):
                print(f"Failed to link ticket {source_ticket} to {target}: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"Error linking ticket {source_ticket} to {target}: {e}")
