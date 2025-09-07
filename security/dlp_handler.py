import re
import json
from typing import Dict, List

# Responsible for Data Loss Prevention (DLP) handling, URL filtering, and redaction

class DLPHandler:
    def __init__(self, config_path: str = "config/dlp_rules.json"):
        with open(config_path) as f:
            self.config = json.load(f)
            
    def check_message(self, text: str, room: str) -> tuple[str, bool]:
        """Returns (processed_text, is_blocked)"""
        # Implementation for Part 2
        return text, False