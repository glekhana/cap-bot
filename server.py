"""
Main application file for the Incentives Bot.
"""
import os
from flask import Flask
from dotenv import load_dotenv
import openai
from waitress import serve
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine


from bot.config.settings import (
    SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, OPENAI_API_KEY,
    DEFAULT_PORT, DEFAULT_HOST
)
from bot.api.slack_routes import register_slack_routes



app = Flask(__name__)

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

# Register routes
register_slack_routes(app)

if __name__ == "__main__":
    # Run the bot
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    host = os.environ.get("HOST", DEFAULT_HOST)
    serve(app, host=host, port=port)