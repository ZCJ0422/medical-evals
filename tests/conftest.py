"""Test-collection defaults for dependencies that construct clients at import time."""

import os


# OpenAI Evals currently creates its Registry client while importing the
# package. Unit and integration tests inject fake clients and must not require
# a real API key or make network calls during collection.
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
