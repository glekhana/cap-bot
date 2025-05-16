"""
Helper functions for interacting with the Slack API.
"""
import json


def get_thread_messages(client, channel_id, thread_ts):
    """
    Get all messages in a thread.
    
    Args:
        client: Slack WebClient instance
        channel_id: ID of the channel containing the thread
        thread_ts: Timestamp of the parent message
        
    Returns:
        List of message objects in the thread
    """
    try:
        # Get thread messages
        result = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts
        )
        return result["messages"] if result.get("ok", False) else []
    except Exception as e:
        print(f"Error retrieving thread messages: {e}")
        return []

def get_full_thread_messages(client,channel_id, thread_ts):
    """
    Retrieves all messages and their attachments in a thread.
    Filters out any messages from Incentives-Bot.

    Args:
        channel_id: The ID of the channel containing the thread
        thread_ts: The timestamp of the parent message

    Returns:
        A list of messages in the thread with their attachments, excluding bot messages
    """
    try:
        # Get all replies in the thread
        result = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts
        )

        all_messages = result.get("messages", [])

        # Format the messages for better readability
        formatted_messages = []
        for msg in all_messages:
            # Get user info
            user_info = client.users_info(user=msg.get("user", "unknown"))
            username = user_info["user"]["real_name"] if user_info.get("ok") else "Unknown User"

            # Skip messages from Incentives-Bot
            if "cap-bot" in username.lower() or "Cap Bot" in username.lower():
                continue

            # Also check if the message is from a bot with the name containing "incentives"
            if msg.get("bot_id") and msg.get("username") and "cap" in msg.get("username", "").lower():
                continue

            # Format the message with timestamp and username
            import datetime
            timestamp = float(msg.get("ts", 0))
            time_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

            # Process files/attachments
            files = []
            if "files" in msg:
                for file in msg["files"]:
                    file_info = {
                        "id": file.get("id"),
                        "name": file.get("name"),
                        "mimetype": file.get("mimetype"),
                        "filetype": file.get("filetype"),
                        "url_private": file.get("url_private"),
                        "permalink": file.get("permalink"),
                        "size": file.get("size")
                    }
                    files.append(file_info)

            formatted_messages.append({
                "username": username,
                "text": msg.get("text", ""),
                "timestamp": time_str,
                "ts": msg.get("ts", ""),
                "is_parent": msg.get("ts") == thread_ts,
                "files": files,
                "attachments": msg.get("attachments", [])  # Keep any message attachments (link unfurls, etc.)
            })

        return formatted_messages

    except Exception as e:
        print(f"Error retrieving thread messages: {e}")
        return []


def upload_files_to_slack(client, channel_id, file_paths, thread_ts=None):
    """
    Upload files to a Slack channel.
    
    Args:
        client: Slack WebClient instance
        channel_id: ID of the channel to upload to
        file_paths: List of file paths to upload
        thread_ts: Optional thread timestamp to attach files to
        
    Returns:
        List of file IDs for the uploaded files
    """
    file_ids = []
    for file_path in file_paths:
        try:
            result = client.files_upload_v2(
                channel=channel_id,
                file=file_path,
                thread_ts=thread_ts
            )
            if result.get("ok", False):
                file_ids.append(result.get("file", {}).get("id"))
        except Exception as e:
            print(f"Error uploading file {file_path}: {e}")
    
    return file_ids

def create_block_message(blocks, channel_id, thread_ts=None, metadata=None):
    """
    Create a message with blocks and optional metadata.
    
    Args:
        blocks: List of block elements
        channel_id: Channel ID to post to
        thread_ts: Optional thread timestamp
        metadata: Optional metadata to include
        
    Returns:
        Dict with message payload
    """
    payload = {
        "channel": channel_id,
        "blocks": blocks
    }
    
    if thread_ts:
        payload["thread_ts"] = thread_ts
        
    if metadata:
        payload["metadata"] = {
            "event_type": metadata.get("event_type", "default"),
            "event_payload": json.dumps(metadata.get("event_payload", {}))
        }
        
    return payload 