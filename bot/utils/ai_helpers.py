"""
Helper functions for interacting with AI services (e.g., OpenAI).
"""
import openai
from openai import OpenAI
from bot.config.settings import OPENAI_API_KEY
import json

from bot.utils.formatters import format_comments
from bot.utils.jira_helpers import extract_comments_from_duplicates

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# def generate_ticket_title(conversation_text):
#     """
#     Generate a concise title for a ticket based on a Slack conversation.
    
#     Args:
#         conversation_text: The Slack conversation text
        
#     Returns:
#         A string containing the generated title
#     """
#     try:
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant that generates title for a bug from a slack conversation about it. The title is directly added to a Jira ticket."},
#                 {"role": "user", "content": f"Create a short, descriptive title for a JIRA ticket based on this Slack conversation:\n\n{conversation_text}. Output only the title and no pre or post text."}
#             ],
#             max_tokens=60,
#             temperature=0.3
#         )
        
#         title = response.choices[0].message.content.strip()
        
#         # Limit title length to 75 characters
#         if len(title) > 75:
#             title = title[:71] + "..."
            
#         return title
        
#     except Exception as e:
#         print(f"Error generating title: {e}")
#         return "Slack Thread Discussion"


def generate_from_thread_ticket_parameters(conversation_text):
    """
    Generate a concise title for a ticket based on a Slack conversation.

    Args:
        conversation_text: The Slack conversation text

    Returns:
        A string containing the generated title
    """
    prompt = f"""
    You are a helpful assistant that generates tittle,summary, priority for a issue or bug from a slack conversation about it. Based on the Slack thread below, extract:
    - A short, relevant title. This title is directly added to a Jira ticket.
    - A  summary that captures the main issue or request and Be as descriptive as possible. 
    - A priority from one of: "Lowest", "Low", "Medium", "High", "Highest"
    Retain technical and contextual keywords used in the thread.

        Slack Thread:
        \"\"\"
        {conversation_text}
        \"\"\"
        
        Respond only in this JSON format:
        
        {{
          "title": "<issue title>",
          "summary": "<summary of the issue>",
          "priority": "<Lowest | Low | Medium | High | Highest>"
        }}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                 "content": "You are a helpful assistant that generates title for a bug from a slack conversation about it. The title is directly added to a Jira ticket."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        result = response.choices[0].message.content.strip()
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            raise ValueError(f"Could not parse response: {result}")

        return result


    except Exception as e:
        print(f"Error generating title: {e}")
        return "Slack Thread Discussion"


# def suggest_priority(conversation_text):
#     """
#     Suggest a priority level based on a Slack conversation.
    
#     Args:
#         conversation_text: The Slack conversation text
        
#     Returns:
#         A string containing the suggested priority (Lowest, Low, Medium, High, Highest)
#     """
#     try:
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant that generates priority for a bug from a slack conversation about it. Based on the conversation, you'll assign one of these priority levels: 'Lowest', 'Low', 'Medium', 'High', or 'Highest'."},
#                 {"role": "user", "content": f"Based on this Slack conversation, determine the appropriate priority level for a JIRA ticket. Return exactly one of these options: 'Lowest', 'Low', 'Medium', 'High', or 'Highest'.\n\n{conversation_text}"}
#             ],
#             max_tokens=20,
#             temperature=0.3
#         )
        
#         priority_text = response.choices[0].message.content.strip()
        
#         # Extract valid priority
#         valid_priorities = ["Lowest", "Low", "Medium", "High", "Highest"]
#         if not any(p.lower() in priority_text.lower() for p in valid_priorities):
#             return "Medium"  # Default
            
#         # Find which priority was mentioned
#         for p in valid_priorities:
#             if p.lower() in priority_text.lower():
#                 return p
                
#         return "Medium"  # Default fallback
        
#     except Exception as e:
#         print(f"Error suggesting priority: {e}")
#         return "Medium"

# def generate_ticket_summary(conversation_text):
#     """
#     Generate a detailed summary for a ticket based on a Slack conversation.
    
#     Args:
#         conversation_text: The Slack conversation text
        
#     Returns:
#         A string containing the generated summary
#     """
#     try:
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant that generates description for a bug from a slack conversation about it. The description is directly added to a Jira ticket."},
#                 {"role": "user", "content": f"Generate a JIRA ticket description for a bug from the following slack conversation:\n\n{conversation_text}. Be as descriptive as possible. Preserve the major keywords"}
#             ],
#             max_tokens=500,
#             temperature=0.3
#         )
        
#         return response.choices[0].message.content.strip()
        
#     except Exception as e:
#         print(f"Error generating summary: {e}")
#         return "No automated summary available. Please refer to the original Slack thread for details."



def analyze_duplicate_issues(duplicates):
    """
    Analyze each duplicate issue and extract comprehensive information.

    Args:
        duplicates: List of dictionaries containing duplicate ticket information

    Returns:
        A list of dictionaries with detailed analysis of each duplicate
    """
    analyzed_duplicates = []

    # Extract all comments from duplicates
    comments_by_ticket = extract_comments_from_duplicates(duplicates)

    for dup in duplicates:
        ticket_key = dup.get('issue_key', '')
        # Get all comments for this ticket
        ticket_comments = comments_by_ticket.get(ticket_key, [])

        try:

            description = dup.get('description', '')
            title = dup.get('title', '') or dup.get('summary', '')

            # Include full comments in the prompt
            comments_text = format_comments(ticket_comments)

            prompt = f"""
            You are an expert analyst examining JIRA tickets. Based on the complete ticket information below, extract:
            - A comprehensive issue summary
            - The detailed root cause analysis (RCA) if available
            - The complete resolution summary if available
            
            Do not omit any important details. Be thorough in your analysis.
            
            Title:
            \"\"\"
            {title}
            \"\"\"
            
            Description:
            \"\"\"
            {description}
            \"\"\"
            
            {comments_text}
            
            Respond only in this JSON format:
            
            {{
              "issue_summary": "<detailed summary of the issue>",
              "rca_summary": "<comprehensive root cause analysis or 'Not available' if not found>",
              "resolution_summary": "<detailed resolution summary or 'Not available' if not found>"
            }}
            """

            response = client.chat.completions.create(
                model="gpt-3.5-turbo-16k",  # Using larger context model to handle more text
                messages=[
                    {"role": "system",
                     "content": "You are an expert technical analyst who extracts comprehensive information from JIRA tickets."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,

            )

            result = response.choices[0].message.content.strip()
            try:
                analysis = json.loads(result)
                # Add the original ticket key and summary for reference
                analysis["issue_key"] = ticket_key
                analysis["comments"] = ticket_comments
                analysis["original_summary"] = dup.get("summary", "")
                analyzed_duplicates.append(analysis)
            except json.JSONDecodeError:
                raise ValueError(f"Could not parse response: {result}")

        except Exception as e:
            print(f"Error analyzing duplicate issue: {e}")
            # Add minimal information for the failed analysis
            analyzed_duplicates.append({
                "key": dup.get("issue_key", ""),
                "original_summary": dup.get("summary", ""),
                "comments":ticket_comments,
                "issue_summary": "Analysis failed",
                "rca_summary": "Not available",
                "resolution_summary": "Not available"
            })

    return analyzed_duplicates

def summarize_duplicate_issues(title, summary, description, duplicates):
    """
    Generate a comprehensive analysis of potential duplicate issues with detailed RCA and solution suggestions.

    Args:
        title: The ticket title
        summary: The ticket summary
        description: The ticket description
        duplicates: List of potential duplicate tickets

    Returns:
        A dictionary with comprehensive analysis focusing on RCA and solution
    """
    try:
        if not duplicates:
            return {
                "analysis": "No similar issues found to determine root cause.",
                "suggested_solution": "No previous solutions to reference."
            }

        # First analyze each duplicate to get comprehensive information
        analyzed_duplicates = analyze_duplicate_issues(duplicates)

        # Format duplicates with their full analysis
        duplicates_text = ""
        for i, dup in enumerate(analyzed_duplicates):  # Include all analyzed duplicates
            comments_text = format_comments(dup["comments"])
            duplicates_text += f"Key: {dup['issue_key']}\n"
            duplicates_text += f"   Title: {dup['original_summary']}\n"
            duplicates_text += f"   Comments in ticket : {comments_text}\n\n"
            duplicates_text += f"   Issue Summary: {dup['issue_summary']}\n"
            duplicates_text += f"   Root Cause: {dup['rca_summary']}\n"
            duplicates_text += f"   Resolution: {dup['resolution_summary']}\n\n"
            duplicates_text += f"--------------------------------------\n\n\n"


        # Extract all comments from duplicates

        # Create master prompt with all available information
        prompt = f"""You are given a new issue along with a list of similar past issues, including their complete descriptions and full comment threads.

        New Issue:
        Title: {title}
        Summary: {summary}
        Description: {description}

        Similar Past Issues (with full details and resolutions):
        {duplicates_text}

        Your task is to perform a comprehensive duplicate analysis and recommend a solution.

        Please provide:
        1. A summary of how the current issue relates to the previous issues. Refer to each past issue by its issue key. Omit any issues that don't relate to current issue.
        2. A concise potential solution, based on how the previous issues were resolved.

        Important guidelines:
        - Be concise and precise in your analysis.
        - Do not omit relevant technical or contextual details.
        - Structure your response clearly with appropriate formatting and line breaks.
        - Avoid generic summaries; ground all conclusions in the provided data.
        - Do not mention any issues that don't match with the current issue.
        - Do not mention any issues that are relevant to the current issue. Skip the ticket if it has not given you valuable information.

        Respond strictly in the following JSON format:

        {{
          "analysis": "<Concise analysis of how current issue relates to previous issues, referencing issue keys, with clear formatting and line breaks>",
          "suggested_solution": "<Potential solution derived from previous resolutions, clearly formatted>"
        }}
        """

        print(prompt)

        response = client.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14", # o4-mini-2025-04-16  # Using larger context model
            messages=[
                {"role": "system", "content": "You are a senior technical analyst specializing in identifying duplicate issues by analyzing current and historical tickets. Your job is to examine new issues in detail, compare them against a set of similar past issues (including their full descriptions and comments), and provide a precise analysis of how they are related. You must also derive a comprehensive solution for the new issue based on how previous issues were resolved. Be exhaustive, use issue keys in your analysis, and structure your output clearly in the requested JSON format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            # temperature=0.3,

        )

        result = response.choices[0].message.content.strip()
        try:
            analysis = json.loads(result)
            return analysis
        except json.JSONDecodeError:
            raise ValueError(f"Could not parse response: {result}")

    except Exception as e:
        print(f"Error analyzing duplicates: {e}")
        return {
            "analysis": "Unable to find similar issues.",
            "suggested_solution": "Please review similar tickets manually to determine appropriate solution."
        }

