"""Pytest configuration for ChambeApp backend tests."""

import os
import pytest

# Set testing environment before importing app
os.environ["TESTING"] = "1"
os.environ["FLASK_TESTING"] = "1"
