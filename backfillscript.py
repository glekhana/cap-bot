import psycopg2
import json
from time import sleep

# Assuming this method is defined exactly as you've shared
from bot.utils.ai_helpers import generate_summary_from_ticket  # Replace with your actual module
from bot.utils.formatters import format_comments
from bot.utils.jira_helpers import get_issue_comments

DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",  # or your DB host
    "port": 5452
}

BATCH_SIZE = 5
TABLE_NAME = "jira_issues"  # Replace with your actual table name

def fetch_unprocessed_tickets(cursor, limit):
    query = f"""
        SELECT id, summary, description,issue_key
        FROM {TABLE_NAME}
        WHERE generated_summary IS NULL
        LIMIT %s;
    """
    cursor.execute(query, (limit,))
    return cursor.fetchall()

def update_generated_summary(cursor, ticket_id, summary_json):
    query = f"""
        UPDATE {TABLE_NAME}
        SET generated_summary = %s
        WHERE id = %s;
    """
    cursor.execute(query, (json.dumps(summary_json), ticket_id))

def process_tickets():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        while True:
            tickets = fetch_unprocessed_tickets(cursor, BATCH_SIZE)
            if not tickets:
                print("✅ All tickets processed.")
                break

            for ticket in tickets:
                ticket_id, summary, description, issue_key = ticket
                print(f"Processing Ticket ID {ticket_id}...")
                # comments = get_issue_comments(issue_key)
                # comments_text = format_comments(comments)
                try:
                    result = generate_summary_from_ticket(summary, description)
                    update_generated_summary(cursor, ticket_id, result)
                    conn.commit()
                    print(f"✅ Updated ticket ID {ticket_id}")
                except Exception as e:
                    print(f"❌ Error processing ticket ID {ticket_id}: {e}")
                    continue

            conn.commit()
            sleep(1)  # Optional: avoid hammering the DB or API

    except Exception as e:
        conn.rollback()
        print(f"🔥 Critical Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    process_tickets()
