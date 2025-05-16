import math
import re

def format_comments(ticket_comments):
    """
    Format JIRA comments by extracting text from Atlassian Document Format (ADF).
    
    Args:
        ticket_comments: List of JIRA comment objects
        
    Returns:
        Formatted string with extracted comment text
    """
    comments_text = ""
    
    if not ticket_comments:
        return comments_text
        
    for i, comment in enumerate(ticket_comments):
        author = comment.get('author', 'Unknown')
        body = comment.get('body', '')
        
        # Extract text from ADF format if body is a dictionary
        if isinstance(body, dict):
            extracted_text = extract_text_from_adf(body)
            comments_text += f"Comment {i + 1} by {author}:\n{extracted_text}\n\n"
        else:
            # If it's already a string, use it directly
            comments_text += f"Comment {i + 1} by {author}:\n{body}\n\n"
            
    return comments_text

def extract_text_from_adf(adf_content):
    """
    Extract plain text from Atlassian Document Format (ADF) structure.
    
    Args:
        adf_content: Dictionary containing ADF content
        
    Returns:
        Extracted plain text
    """
    if not isinstance(adf_content, dict):
        return str(adf_content)
        
    # Check if it's ADF format
    if 'content' in adf_content and isinstance(adf_content['content'], list):
        # Extract text from all content nodes recursively
        return extract_text_from_nodes(adf_content['content'])
    
    # If not recognized ADF format, convert to string
    return str(adf_content)

def extract_text_from_nodes(nodes):
    """
    Recursively extract text from ADF content nodes.
    
    Args:
        nodes: List of ADF nodes
        
    Returns:
        Concatenated text from all nodes
    """
    if not isinstance(nodes, list):
        return ""
        
    extracted_text = ""
    
    for node in nodes:
        if not isinstance(node, dict):
            continue
            
        # Text node contains the actual text
        if node.get('type') == 'text' and 'text' in node:
            extracted_text += node['text']
            
        # For other node types, recursively process their content
        elif 'content' in node and isinstance(node['content'], list):
            extracted_text += extract_text_from_nodes(node['content'])
            
        # Handle line breaks for paragraph nodes
        if node.get('type') == 'paragraph' and extracted_text and not extracted_text.endswith('\n'):
            extracted_text += '\n'
            
    return extracted_text
def trim_float(value, decimals=3):
    percent = value * 100
    return f"{percent:.{decimals}f}%"


def replace_double_with_single_asterisks(text):
    return re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
