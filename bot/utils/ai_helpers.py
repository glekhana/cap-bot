"""
Helper functions for interacting with AI services (e.g., OpenAI).
"""
import openai
from openai import OpenAI
from bot.config.settings import OPENAI_API_KEY
import json,time
import threading
from bot.models.updateData import update_generated_summary, update_multiple_generated_summary
from bot.services.anonymization import anonymize_pii, de_anonymize_pii
from bot.utils.formatters import format_comments
from bot.utils.jira_helpers import extract_comments_from_duplicates, get_issue_comments

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


def generate_from_thread_ticket_parameters(conversation_text):

    anonymized_conversation_text,mappings = anonymize_pii(conversation_text)

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
        {anonymized_conversation_text}
        \"\"\"
        
        Respond only in this JSON format:
        
        {{
          "title": "<issue title>",
          "summary": "<summary of the issue>",
          "priority": "<Lowest | Low | Medium | High | Highest>"
        }}
"""
    print("----------Anonymzed Conversation-------")
    print(anonymized_conversation_text)
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
        result = de_anonymize_pii(result,mappings)
        print("----------De Anonymzed Summary-------")
        print(result)
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            raise ValueError(f"Could not parse response: {result}")

        return result


    except Exception as e:
        print(f"Error generating title: {e}")
        return "Slack Thread Discussion"


def generate_summary_from_ticket(title,description,comments_text="None for now"):
    try:

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
        anonymized_prompt,mappings = anonymize_pii(prompt)

        response = client.chat.completions.create(
            model="gpt-3.5-turbo-16k",  # Using larger context model to handle more text
            messages=[
                {"role": "system",
                 "content": "You are an expert technical analyst who extracts comprehensive information from JIRA tickets."},
                {"role": "user", "content": anonymized_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,

        )

        result = response.choices[0].message.content.strip()
        final_result = de_anonymize_pii(result,mappings)
        try:
            result = json.loads(final_result)

        except json.JSONDecodeError:
            raise ValueError(f"Could not parse response: {result}")
        return result
    except Exception as e:
        print(f"Error analyzing duplicate issue: {e}")
        # Add minimal information for the failed analysis
        return {
            "issue_summary": "Not available",
            "rca_summary": "Not available",
            "resolution_summary": "Not available"
        }


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
    start_time = time.time()


    save_to_db = []
    for dup in duplicates:
        ticket_key = dup.get('issue_key', '')

        try:
            if dup['generated_summary'] is  None:
                comments = get_issue_comments(ticket_key)
                result = summarize_for_individual_issue(dup, comments)
                try:
                    analysis = json.loads(result)
                    issue = {
                        "generated_summary": analysis,
                        "issue_key": ticket_key
                    }
                    save_to_db.append(issue)
                    analysis["issue_key"] = ticket_key

                    analysis["original_summary"] = dup.get("summary", "")
                    save_to_db.append(analysis)

                except json.JSONDecodeError:
                    raise ValueError(f"Could not parse response: {result}")
            else:
                analysis=dup['generated_summary']
                analysis["issue_key"] = ticket_key
                analysis["original_summary"] = dup.get("summary", "")
            analyzed_duplicates.append(analysis)

        except Exception as e:
            print(f"Error analyzing duplicate issue: {e}")
            # Add minimal information for the failed analysis
            analyzed_duplicates.append({
                "key": dup.get("issue_key", ""),
                "original_summary": dup.get("summary", ""),
                "issue_summary": "Analysis failed",
                "rca_summary": "Not available",
                "resolution_summary": "Not available"
            })
            continue
    if save_to_db is not None:
        thread = threading.Thread(
            target=update_multiple_generated_summary,
            args=(save_to_db,)
        )
        thread.daemon = True
        thread.start()
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

            duplicates_text += f"Key: {dup['issue_key']}\n"
            duplicates_text += f"   Title: {dup['original_summary']}\n"
            #duplicates_text += f"   Comments in ticket : {comments_text}\n\n"
            duplicates_text += f"   Issue Summary: {dup['issue_summary']}\n"
            duplicates_text += f"   Root Cause: {dup['rca_summary']}\n"
            duplicates_text += f"   Resolution: {dup['resolution_summary']}\n\n"
            duplicates_text += f"--------------------------------------\n\n\n"

        # Create master prompt with all available information
        prompt = f"""You are given a new issue along with a list of similar past issues, including their complete descriptions.

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
        - Give each point in bulleted format
        - Keep the content to the point and concise
        - Make sure if any ticket is mentioned in analysis always keep the ticket ids in bold

        Respond strictly in the following JSON format:

        {{
          "analysis": "<Concise analysis of how current issue relates to previous issues, referencing issue keys, with clear formatting and line breaks>",
          "suggested_solution": "<Potential solution derived from previous resolutions, clearly formatted>"
        }}
        """


        anonymized_prompt,mappings = anonymize_pii(prompt)

        response = client.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14", # o4-mini-2025-04-16  # Using larger context model
            messages=[
                {"role": "system", "content": "You are a senior technical analyst specializing in identifying duplicate issues by analyzing current and historical tickets. Your job is to examine new issues in detail, compare them against a set of similar past issues (including their full descriptions and comments), and provide a precise analysis of how they are related. You must also derive a comprehensive solution for the new issue based on how previous issues were resolved. Be exhaustive, use issue keys in your analysis, and structure your output clearly in the requested JSON format."},
                {"role": "user", "content": anonymized_prompt}
            ],
            response_format={"type": "json_object"},
            # temperature=0.3,

        )

        result = response.choices[0].message.content.strip()
        result = de_anonymize_pii(result,mappings)
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
def summarize_for_individual_issue(dup,ticket_comments):
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
    anonymize_prompt,mappings = anonymize_pii(prompt)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-16k",  # Using larger context model to handle more text
        messages=[
            {"role": "system",
             "content": "You are an expert technical analyst who extracts comprehensive information from JIRA tickets."},
            {"role": "user", "content": anonymize_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,

    )

    result = response.choices[0].message.content.strip()

    return de_anonymize_pii(result,mappings)
