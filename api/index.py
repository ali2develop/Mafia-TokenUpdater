"""
Vercel serverless function entry point.
This file is required for Vercel to properly route requests.
"""

from app import app

# Vercel expects a variable named 'app' or a handler function
# Flask app is already defined in app.py