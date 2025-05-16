"""
Routes for Slack API interactions.
"""
import json
import threading
from flask import request, jsonify

from bot.config.settings import (
    SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, COMPONENT_SEARCH_URL, REPOS, JIRA_PROJECT_KEY
)
from bot.handlers.event_handlers import handle_ticket_modal_submission, create_thread_to_ticket_async, \
    register_issue_update,register_comment_update
from bot.handlers.ticket_handlers import (
    handle_thread_to_ticket_async, show_ticket_creation_form
)
from bot.handlers.release_handlers import handle_submission_async
from bot.models.updateData import index_issue
from bot.utils.jira_helpers import get_project_components, get_jira_projects
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier

# Initialize Slack clients
client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(SLACK_SIGNING_SECRET)





def register_slack_routes(app):
    """
    Register Slack-related routes with the Flask bot.
    
    Args:
        app: Flask application instance
    """
    
    @app.route("/slack/commands", methods=["POST"])
    def slack_commands():
        if not verifier.is_valid_request(request.get_data(), request.headers):
            return "Invalid request", 403

        data = request.form
        command = data.get("command")
        trigger_id = data.get("trigger_id")
        channel_id = data.get("channel_id")

        if command == "/generate-release-ticket":
            options = [
                {
                    "text": {"type": "plain_text", "text": repo},
                    "value": repo
                } for repo in REPOS
            ]

            # Create the modal blocks with all form fields
            blocks = [
                {
                    "type": "input",
                    "block_id": "repo_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "repo_select",
                        "placeholder": {"type": "plain_text", "text": "Select a repository"},
                        "options": options
                    },
                    "label": {"type": "plain_text", "text": "Repository"}
                },
                {
                    "type": "input",
                    "block_id": "tag1_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "tag1_input",
                        "placeholder": {"type": "plain_text", "text": "e.g., v1.6"}
                    },
                    "label": {"type": "plain_text", "text": "Old Tag"}
                },
                {
                    "type": "input",
                    "block_id": "tag2_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "tag2_input",
                        "placeholder": {"type": "plain_text", "text": "e.g., v1.7"}
                    },
                    "label": {"type": "plain_text", "text": "New Tag"}
                },
                {
                    "type": "input",
                    "block_id": "ticket_name_block",
                    "optional": True,
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "ticket_name_input",
                        "placeholder": {"type": "plain_text", "text": "Optional ticket name"}
                    },
                    "label": {"type": "plain_text", "text": "Ticket Name"}
                },
                {
                    "type": "section",
                    "block_id": "append_mode_block",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Append Mode:* Select to append to an existing ticket"
                    },
                    "accessory": {
                        "type": "checkboxes",
                        "action_id": "append_mode_checkbox",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Append to existing ticket"
                                },
                                "value": "append_mode"
                            }
                        ]
                    }
                },
                {
                    "type": "input",
                    "block_id": "existing_ticket_block",
                    "optional": True,
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "existing_ticket_input",
                        "placeholder": {"type": "plain_text", "text": "e.g., NBP-123"}
                    },
                    "label": {"type": "plain_text", "text": "Existing Ticket ID (for append mode)"}
                }
            ]

            client.views_open(
                trigger_id=trigger_id,
                view={
                    "type": "modal",
                    "callback_id": "release_notes_modal",
                    "title": {"type": "plain_text", "text": "Generate Release Notes"},
                    "submit": {"type": "plain_text", "text": "Generate"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "private_metadata": channel_id,
                    "blocks": blocks
                }
            )
            return "", 200

        return jsonify({"text": "Unknown command."})
    
    @app.route("/slack/menus", methods=["POST"])
    def get_components():
        """
        Handle external data source for component selection.
        This endpoint returns components matching a search query.
        """
        try:
            print("Received request to /slack/get_components")
            
            # Debug raw request data
            request_data = request.get_data()
            print(f"Raw request data: {request_data}")
            
            # Skip signature verification for now to simplify testing
            # if not verifier.is_valid_request(request.get_data(), request.headers):
            #     print("Invalid request signature")
            #     return jsonify({"error": "Invalid request"}), 403

            # Parse the payload - handle different possible formats
            payload = None
            value = ""
            
            # If form data with 'payload' key
            if request.form and 'payload' in request.form:
                try:
                    payload_str = request.form.get('payload')
                    print(f"Form payload: {payload_str}")
                    payload = json.loads(payload_str)
                    value = payload.get("value", "")
                except json.JSONDecodeError as e:
                    print(f"Error parsing form payload: {e}")
            
            # If direct JSON body
            elif request.is_json:
                payload = request.get_json()
                print(f"JSON payload: {payload}")
                value = payload.get("value", "")
            
            # If direct form data without 'payload' wrapper
            elif request.form:
                print(f"Direct form data: {request.form}")
                payload = dict(request.form)
                value = payload.get("value", "")
            
            # Default empty payload for fallback
            if not payload:
                print("No valid payload found, using defaults")
                payload = {}
                value = ""

            # Get project key from the action
            project_key = None

            # Try to get project key from state
            if "state" in payload and "values" in payload["state"]:
                state_values = payload["state"]["values"]
                if "project_block" in state_values and "project_select" in state_values["project_block"]:
                    selected_option = state_values["project_block"]["project_select"].get("selected_option")
                    if selected_option:
                        project_key = selected_option.get("value")
                        print(f"Found project key in state: {project_key}")

            # Fallback to default project if not found
            if not project_key:
                project_key = JIRA_PROJECT_KEY
                print(f"Using default project key: {project_key}")

            # Get components for the selected project - ALWAYS use target JIRA
            components = get_project_components(project_key, use_target_jira=True)

            # Filter components based on search query
            if value:
                filtered_components = [
                    component for component in components
                    if value.lower() in component.get("name", "").lower()
                ]
                print(f"Filtered to {len(filtered_components)} components matching '{value}'")
            else:
                filtered_components = components[:20]  # Limit to 20 if no search query
                print(f"No search query, returning first {len(filtered_components)} components")

            # Format options for Slack
            options = []
            for component in filtered_components[:100]:  # Limit to 100 max results
                options.append({
                    "text": {
                        "type": "plain_text",
                        "text": component.get("name", "")
                    },
                    "value": component.get("id", "")
                })
            
            # Debug the response
            response = {"options": options}
            print(f"Returning response with {len(options)} options")
            
            # Return formatted response according to Slack's external_select requirements
            return jsonify(response)

        except Exception as e:
            print(f"Error getting component options: {e}")
            # Return empty options array with HTTP 200 when an error occurs
            # This ensures Slack doesn't show an error to the user
            return jsonify({
                "options": []
            }), 200
    
    @app.route("/slack/interactions", methods=["POST"])
    def handle_interactions():
        """
        Handle interactive components from Slack.
        """
        # Verify the request signature
        if not verifier.is_valid_request(request.get_data(), request.headers):
            return "Invalid request", 403

        payload = json.loads(request.form.get("payload"))

        # Handle message shortcut
        if payload.get("type") == "message_action" and payload.get("callback_id") == "create_jira_from_thread":
            # Get necessary information from the payload
            channel_id = payload.get("channel", {}).get("id")
            message_ts = payload.get("message", {}).get("ts")
            user_id = payload.get("user", {}).get("id")
            response_url = payload.get("response_url")
            import threading
            # Acknowledge the request immediately and start the new flow
            threading.Thread(
                target=handle_thread_to_ticket_async,
                args=(user_id, channel_id, message_ts, response_url)
            ).start()

            return "", 200

        # Handle block actions (like buttons)
        elif payload.get("type") == "block_actions":
            actions = payload.get("actions", [])
            
            if not actions:
                return "", 200
            
            action = actions[0]
            action_id = action.get("action_id", "")
            
            # Handle event with a project selection - update components dropdown
            if action_id == "project_select":
                # Project selection changed - load available components for this project
                selected_project = action.get("selected_option", {}).get("value")
                
                if selected_project:
                    # This will be handled client-side with JavaScript to update the components dropdown
                    # We'll just log it for now
                    print(f"Project selected: {selected_project}")
                
                return "", 200
            elif action_id == "open_ticket_form":
                trigger_id = payload.get("trigger_id")
                user_id = payload.get("user", {}).get("id", "")
                channel_id = payload.get("channel", {}).get("id", "")
                message = payload.get("message", {})
                message_ts = message.get("ts", "")
                thread_ts = message.get("thread_ts", message_ts)

                # Get value from the button
                value = json.loads(action.get("value", "{}"))
                has_duplicates = value.get("has_duplicates", False)
                summary = value.get("summary","")
                priority = value.get("priority","Medium")
                analysis = value.get("analysis", "")
                title = value.get("title","")
                suggested_solution = value.get("solution", "")




                try:
                    result = client.conversations_replies(
                        channel=channel_id,
                        ts=thread_ts
                    )

                except Exception as e:
                    print(f"Error retrieving thread messages: {e}")
                    title = "Ticket from Slack"

                # Construct ticket context
                ticket_context = {
                    "channel_id": channel_id,
                    "message_ts": thread_ts,
                    "title": title,
                    "priority": priority,  # Default priority
                    "user_id": user_id,
                    "analysis":analysis,
                    "summary":summary,
                    "suggested_solution":suggested_solution,
                    "trigger_id": trigger_id
                }

                # Show the ticket creation form
                show_ticket_creation_form(ticket_context, has_duplicates=has_duplicates)
                return {"text": "Opening ticket creation form..."}
          # Handle view submissions (e.g., from modals)
        elif payload.get("type") == "view_submission":
            view = payload.get("view", {})
            callback_id = view.get("callback_id")
            if callback_id == "ticket_creation_modal":
                try:
                    # Extract form values
                    state = view.get("state", {}).get("values", {})
                    response_url = payload.get("response_url")

                    # Get form fields
                    title = state.get("title_block", {}).get("title_input", {}).get("value", "")

                    # Get summary from the new summary field
                    summary = state.get("summary_block", {}).get("summary_input", {}).get("value", "")

                    project_select = state.get("project_block", {}).get("project_select", {})
                    project = project_select.get("selected_option", {}).get("value", "")

                    priority_select = state.get("priority_block", {}).get("priority_select", {})
                    priority = priority_select.get("selected_option", {}).get("value", "")

                    labels = state.get("labels_block", {}).get("labels_input", {}).get("value", "")

                    component_select = state.get("component_block", {}).get("component_select", {})
                    component = None
                    if "selected_option" in component_select:
                        component = component_select["selected_option"]["value"]

                    # Get metadata
                    metadata = view.get("private_metadata", "{}")
                    ticket_context = json.loads(metadata)

                    # Update with form values
                    ticket_context["title"] = title
                    ticket_context["summary"] = summary  # Save the summary
                    ticket_context["project"] = project
                    ticket_context["priority"] = priority
                    ticket_context["labels"] = labels.split(",") if labels else []
                    if component:
                        ticket_context["component"] = component

                    # Get user info
                    user_id = payload.get("user", {}).get("id", "")
                    ticket_context["user_id"] = user_id

                    # Get channel info for notifications
                    channel_id = ticket_context.get("channel_id")
                    message_ts = ticket_context.get("message_ts")

                    # Process asynchronously to avoid blocking response
                    # Use a separate thread or queue this task
                    import threading
                    thread = threading.Thread(
                        target=create_thread_to_ticket_async,
                        args=(client,user_id, channel_id, message_ts, response_url,ticket_context)
                    )
                    thread.daemon = True  # Allow bot to exit even if thread is running
                    thread.start()

                    print(f"Started ticket creation thread for user {user_id}")

                    # Send an immediate notification in the thread about ticket creation

                    client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text="🔄 Your JIRA ticket is being created. You will be notified when it's complete."
                    )
                    return "", 200

                except Exception as e:
                    print(f"Error processing form: {e}")
                    import traceback
                    traceback.print_exc()

                # Return a response to close the modal
                return {"response_action": "clear"}


            elif callback_id == "release_notes_modal":
                # Process release notes modal submission
                try:
                    # Get the channel ID from private metadata
                    channel_id = view.get("private_metadata")
                    
                    # Get values from the view state
                    state_values = view.get("state", {}).get("values", {})
                    
                    # Extract repository and tags
                    repo = state_values.get("repo_block", {}).get("repo_select", {}).get("selected_option", {}).get("value")
                    tag1 = state_values.get("tag1_block", {}).get("tag1_input", {}).get("value")
                    tag2 = state_values.get("tag2_block", {}).get("tag2_input", {}).get("value")
                    
                    # Extract optional ticket name
                    ticket_name = state_values.get("ticket_name_block", {}).get("ticket_name_input", {}).get("value")
                    
                    # Check if in append mode
                    append_mode = len(state_values.get("append_mode_block", {}).get("append_mode_checkbox", {}).get("selected_options", [])) > 0
                    
                    # Get existing ticket ID if in append mode
                    existing_ticket_id = None
                    if append_mode:
                        existing_ticket_id = state_values.get("existing_ticket_block", {}).get("existing_ticket_input", {}).get("value")
                    
                    # Get the user who submitted the form
                    user_id = payload.get("user", {}).get("id")
                    
                    # Validate inputs
                    if not repo or not tag1 or not tag2:
                        return {
                            "response_action": "errors",
                            "errors": {
                                "repo_block": "Please select a repository." if not repo else None,
                                "tag1_block": "Please enter the old tag." if not tag1 else None,
                                "tag2_block": "Please enter the new tag." if not tag2 else None
                            }
                        }
                    
                    # Validate existing ticket ID if in append mode
                    if append_mode and not existing_ticket_id:
                        return {
                            "response_action": "errors",
                            "errors": {
                                "existing_ticket_block": "Please enter an existing ticket ID for append mode."
                            }
                        }
                    
                    # Post a message to the channel
                    thread_ts = None
                    message = client.chat_postMessage(
                        channel=channel_id,
                        text=f"🔄 Generating release notes for *{repo}* from tag `{tag1}` to `{tag2}`..."
                    )
                    
                    if message.get("ok"):
                        thread_ts = message.get("ts")
                    import threading
                    # Start the processing thread
                    threading.Thread(
                        target=handle_submission_async,
                        args=(user_id, repo, tag1, tag2, channel_id, thread_ts, ticket_name, existing_ticket_id)
                    ).start()
                    
                    # Return a success response to close the modal
                    return {"response_action": "clear"}
                    
                except Exception as e:
                    print(f"Error processing modal submission: {e}")
                    # Return an error response
                    return {
                        "response_action": "errors",
                        "errors": {
                            "repo_block": "An error occurred. Please try again."
                        }
                    }
            
            return {"response_action": "clear"}

        return "", 200
    
    @app.route("/", methods=["GET"])
    def ping():
        """
        Simple status endpoint.
        """
        return """
        <html>
            <head>
                <title>Release Bot Status</title>
                <style>
                    body {
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background-color: #f4f6f8;
                        text-align: center;
                        padding: 50px;
                    }
                    .box {
                        background-color: #ffffff;
                        border-radius: 12px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                        display: inline-block;
                        padding: 40px 60px;
                    }
                    h1 {
                        color: #2c3e50;
                        margin-bottom: 10px;
                    }
                    p {
                        font-size: 18px;
                        color: #34495e;
                    }
                </style>
            </head>
            <body>
                <div class="box">
                    <h1>🤖 Release Bot is Online!</h1>
                    <p>Ready to fetch PRs, extract Jira tickets, and create sparkling release notes. ✨</p>
                    <p><strong>Try a POST to <code>/trigger-release</code> with:</strong></p>
                    <ul style="list-style: none; padding: 0;">
                        <li>📦 <strong>repo</strong>: your repo name</li>
                        <li>🔖 <strong>tag1</strong>: old tag</li>
                        <li>🆕 <strong>tag2</strong>: new tag</li>
                    </ul>
                    <p>Let the automation begin! 🚀</p>
                </div>
            </body>
        </html>
        """, 200

    @app.route('/update-status', methods=['POST'])
    def update_status_endpoint():
        try:
            data = request.json
            register_issue_update(client, data)
            return jsonify({
                'success': True,
                'message': f'Successfully updated status'
            }), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/add-issue', methods=['POST'])
    def add_issue_endpoint():
        try:
            data = request.json
            print(data)

            # Extract issue data from the webhook payload
            if not data or 'issue' not in data:
                return jsonify({
                    'success': False,
                    'error': 'Invalid webhook payload: missing issue data'
                }), 400

            issue_data = data['issue']
            fields = issue_data.get('fields', {})

            # Prepare the data for add_issue function
            issue_info = {
                'key': issue_data.get('key'),
                'summary': fields.get('summary'),
                'description': fields.get('description'),
                'status': fields.get('status', {}).get('name'),
                'priority': fields.get('priority', {}).get('name'),
                'issuetype': fields.get('issuetype', {}).get('name'),
                'project': fields.get('project', {}).get('key'),
                'created': fields.get('created'),
                'updated': fields.get('updated'),
                'reporter': fields.get('reporter', {}).get('displayName'),
                'assignee': fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None
            }

            # Validate required fields
            if not issue_info['key'] or not issue_info['summary']:
                return jsonify({
                    'success': False,
                    'error': 'Missing required fields: key and summary are required'
                }), 400

            print(issue_info)
            # Call add_issue function
            success = index_issue(issue_info)

            if success:
                return jsonify({
                    'success': True,
                    'message': f'Successfully added issue {issue_info["key"]}'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': f'Failed to add issue {issue_info["key"]}'
                }), 500

        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/update-comment', methods=['POST'])
    def update_comment_endpoint():
        try:
            data = request.json
            register_comment_update(data)
            return jsonify({
                'success': True,
                'message': f'Successfully updated status'
            }), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/update-comment', methods=['POST'])
    def update_comment_endpoint():
        try:
            data = request.json
            register_comment_update(data)
            return jsonify({
                'success': True,
                'message': f'Successfully updated status'
            }), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500