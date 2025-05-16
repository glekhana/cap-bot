import os

import psycopg2
from psycopg2.extras import Json

def fetch_description_title(issue_key):
    try:
        # Get embedding

        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5452"),
            dbname=os.getenv("PGDATABASE", "postgres"),
            user=os.getenv("PGUSER", ""),
            password=os.getenv("PGPASSWORD", "")
        )
        cur = conn.cursor()

        query = f"""
             SELECT id, summary, description,issue_key
             FROM jira_issues
             WHERE issue_key=%s;
         """
        cur.execute(query, (issue_key,))

        ticket =  cur.fetchone()
        cur.close()
        print(f"Successfully stored issue {issue_key}")
        return ticket




    except Exception as e:
        print(f"Failed to store issue {issue_key}: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

