"""Shared test configuration — loads .env before any test module is imported."""

from dotenv import load_dotenv

load_dotenv()
