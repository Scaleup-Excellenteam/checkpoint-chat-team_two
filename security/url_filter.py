import re
from typing import List

# Responsible for URL filtering and reputation checking

class URLFilter:
    URL_PATTERN = re.compile(r'https?://[^\s]+')
    
    def __init__(self, reputation_file: str = "config/url_reputation.json"):
        self.load_reputation_list(reputation_file)
    
    def extract_urls(self, text: str) -> List[str]:
        return self.URL_PATTERN.findall(text)
    
    def check_url(self, url: str) -> str:
        """Returns: 'safe', 'suspicious', 'blocked'"""
        # Implementation for Part 2
        return 'safe'