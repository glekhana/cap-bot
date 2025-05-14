# search_jira_proc.py
import os
from openai import OpenAI
import psycopg2
import psycopg2.extras
import json
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from openai import OpenAI
from bot.config.settings import OPENAI_API_KEY

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)
MODEL = "text-embedding-3-small"


def search_issues_via_proc(query_text, top_k=5, alpha=0.8, min_score=0.65):
    logger.info(f"Starting search for query: '{query_text}' with top_k={top_k}, alpha={alpha}")

    try:
        # 1. Get query embedding
        logger.debug("Generating embedding for query")
        resp = client.embeddings.create(model=MODEL, input=query_text)
        q_emb = resp.data[0].embedding
        logger.debug("Successfully generated embedding")

        # 2. Call stored procedure
        logger.info("Connecting to database")
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "localhost"),
            dbname=os.getenv("PGDATABASE", "postgres"),
            user=os.getenv("PGUSER", ""),
            password=os.getenv("PGPASSWORD", "")
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        logger.debug("Executing search stored procedure")
        cur.execute(
            "SELECT * FROM search_jira_issues(%s, %s, %s, %s, %s)",
            (json.dumps(q_emb), query_text, top_k, alpha, min_score)
        )
        results = cur.fetchall()
        logger.info(f"Found {len(results)} matching results")

        cur.close()
        conn.close()
        logger.debug("Database connection closed")

        # 3. Map to dict
        return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"Error during search: {str(e)}", exc_info=True)
        raise



# if __name__ == "__main__":
#     try:
#         hits = search_issues_via_proc("""
#        bhavyadeep bhavyadeep bhavyadeep
#
#         """)
#         for h in hits:
#             print(f"{h['issue_key']} ({h['combined_score']:.3f}): {h['summary']}")
#     except Exception as e:
#         logger.error(f"Error in main execution: {str(e)}", exc_info=True)
