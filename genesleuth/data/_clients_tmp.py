"""Temporary local copy of the section-5c Gemini client lines (delete once genesleuth/gemini_clients.py is on main)."""
from google import genai

client = genai.Client()                                              # stable v1: Interactions API model calls
beta_client = genai.Client(http_options={"api_version": "v1beta"})   # Managed Agents, Environments, Decisions API
