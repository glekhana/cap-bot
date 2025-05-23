import json
import os
import logging
import psycopg2
from openai import OpenAI
import tiktoken
from dotenv import load_dotenv
from psycopg2._json import Json

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
        summary = json.dumps(issue.get("generated_summary"))
        # Insert the issue
        cur.execute(
            """
            INSERT INTO jira_issues
                (issue_key, summary, description, status, priority, issuetype, components,generated_summary, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                summary,
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

def update_generated_summary(issue):

    try:

        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5452"),
            dbname=os.getenv("PGDATABASE", "postgres"),
            user=os.getenv("PGUSER", ""),
            password=os.getenv("PGPASSWORD", "")
        )
        cur = conn.cursor()


        update_query = """
        UPDATE jira_issues
        SET
            generated_summary = %s
        WHERE issue_key = %s;
        """

        cur.execute(update_query, (json.dumps(issue["generated_summary"] ),issue["issue_key"]))
        conn.commit()

        cur.close()
        conn.close()
        print(f"Successfully stored issue {issue['issue_key']}")
        return True

    except Exception as e:
        print(f"Failed to store issue {issue['issue_key']}: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False


def update_multiple_generated_summary(issues):
    # Connect to database
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5452"),
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", ""),
        password=os.getenv("PGPASSWORD", "")
    )
    cur = conn.cursor()
    for issue in issues:
        try:
            update_query = """
            UPDATE jira_issues
            SET
                generated_summary = %s
            WHERE issue_key = %s;
            """

            cur.execute(update_query, (json.dumps(issue["generated_summary"]), issue["issue_key"]))
            conn.commit()


            print(f"Successfully stored issue {issue['issue_key']}")
        except Exception as e:
            print(f"Failed to store issue {issue['issue_key']}: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
            continue

    cur.close()
    conn.close()


def update_all_issue_data(issue):
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


        update_query = """
        UPDATE jira_issues
        SET
            summary = %s,
            description = %s,
            generated_summary = %s,
            embedding = %s
        WHERE issue_key = %s;
        """

        cur.execute(update_query, (issue["summary"] , issue["description"] , json.dumps(issue["generated_summary"] ),emb, issue["issue_key"]))
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

