import os
import logging
import psycopg2
from openai import OpenAI
import tiktoken
from dotenv import load_dotenv
from bot.config.settings import (
    OPENAI_API_KEY,
)


def index_issue(issue):
    # Constants
    MODEL = "text-embedding-3-small"
    MAX_TOKENS = 8191  # model's input limit

    """
    Store a single Jira issue in the database with its embedding.

    Args:
        issue (dict): A dictionary containing the Jira issue data

    Returns:
        bool: True if successful, False otherwise
    """
    # Initialize OpenAI client and tokenizer
    client = OpenAI(api_key=OPENAI_API_KEY)
    enc = tiktoken.get_encoding("cl100k_base")

    # Prepare text and get embedding
    text = issue["summary"] + "\n\n" + (issue.get("description") or "")
    tokens = enc.encode(text)

    # Truncate if too long
    if len(tokens) > MAX_TOKENS:
        tokens = tokens[:MAX_TOKENS]
        text = enc.decode(tokens)

    try:
        # Get embedding
        resp = client.embeddings.create(model=MODEL, input=text)
        emb = resp.data[0].embedding

        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5452"),
            dbname=os.getenv("PGDATABASE", "postgres"),
            user=os.getenv("PGUSER", ""),
            password=os.getenv("PGPASSWORD", "")
        )
        cur = conn.cursor()

        # Insert the issue
        cur.execute(
            """
            INSERT INTO jira_issues
                (issue_key, summary, description, status, priority, issuetype, components, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (issue_key) DO NOTHING
            """,
            (
                issue["key"],
                issue["summary"],
                issue.get("description"),
                issue.get("status"),
                issue.get("priority"),
                issue.get("issuetype"),
                issue.get("components"),
                emb
            )
        )

        conn.commit()
        cur.close()
        conn.close()
        print(f"Successfully stored issue {issue['key']}")
        return True

    except Exception as e:
        print(f"Failed to store issue {issue['key']}: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False
