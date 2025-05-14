"""
Settings and configuration for the application.
Loads environment variables and provides configuration values for the application.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# GitHub Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_USER_NAME = os.getenv("REPO_USER_NAME")

# Source JIRA - for searching duplicates (read-only access)
SOURCE_JIRA_URL = os.getenv("SOURCE_JIRA_URL", os.getenv("JIRA_URL"))
SOURCE_JIRA_ISSUE_URL = os.getenv("SOURCE_JIRA_ISSUE_URL", os.getenv("JIRA_ISSUE_URL"))
SOURCE_JIRA_USER = os.getenv("SOURCE_JIRA_USER", os.getenv("JIRA_USER"))
SOURCE_JIRA_API_TOKEN = os.getenv("SOURCE_JIRA_API_TOKEN", os.getenv("JIRA_API_TOKEN"))
SOURCE_JIRA_PROJECT_KEY = os.getenv("SOURCE_JIRA_PROJECT_KEY", os.getenv("JIRA_PROJECT_KEY"))

# Target JIRA - for creating tickets (write access)
JIRA_URL = os.getenv("JIRA_URL")
JIRA_ISSUE_URL = os.getenv("JIRA_ISSUE_URL")
JIRA_USER = os.getenv("JIRA_USER")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

# Slack Configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Other settings
DEFAULT_PORT = int(os.getenv("PORT", 9000))
DEFAULT_HOST = os.getenv("HOST", "0.0.0.0")

# Repository list configuration
REPOS = os.getenv("REPOS", "SampleTest,incentives-bot").split(",")

# Component search URL
COMPONENT_SEARCH_URL = os.getenv("COMPONENT_SEARCH_URL", "https://lbwq5sv6-9000.inc1.devtunnels.ms/slack/get_components") 