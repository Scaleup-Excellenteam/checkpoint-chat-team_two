import re
import json
import aiohttp
from typing import List, Dict, Any

# Responsible for URL filtering and reputation checking

class URLFilter:
    URL_PATTERN = re.compile(r'https?://[^\s]+|(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?')
    
    def __init__(self, reputation_file: str = "config/dlp_rules.json"):
        self.reputation_data = {}
        self.load_reputation_list(reputation_file)

    
    def load_reputation_list(self, reputation_file: str):
        """Load URL reputation data from config file"""
        try:
            with open(reputation_file, 'r') as f:
                self.reputation_data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: {reputation_file} not found, using default categories")
            # Use categories from dlp_rules.json if available
            try:
                with open("config/dlp_rules.json", 'r') as f:
                    dlp_data = json.load(f)
                    trusted_domains = dlp_data.get('url_filtering', {}).get('trusted_domains', [])
                    self.reputation_data = {
                        "categories": {
                            "tech": trusted_domains,
                            "sport": ["espn.com", "sports.com", "nfl.com", "nba.com"],
                            "news": ["cnn.com", "bbc.com", "reuters.com", "news.com"],
                            "social": ["facebook.com", "twitter.com", "instagram.com"]
                        },
                        "malicious": ["malware.com", "phishing.com", "virus.com"]
                    }
            except:
                self.reputation_data = {
                    "categories": {
                        "sport": ["espn.com", "sports.com", "nfl.com", "nba.com"],
                        "news": ["cnn.com", "bbc.com", "reuters.com", "news.com"],
                        "social": ["facebook.com", "twitter.com", "instagram.com"],
                        "tech": ["github.com", "stackoverflow.com", "google.com"]
                    },
                    "malicious": ["malware.com", "phishing.com", "virus.com"]
                }
    
    def extract_urls(self, text: str) -> List[str]:
        return self.URL_PATTERN.findall(text)
    
    async def check_url_with_virustotal(self, url: str) -> tuple[str, str]:
        """Check URL with VirusTotal API - returns (status, category)"""
        try:
            vt_config = self.reputation_data.get('url_filtering', {}).get('virustotal', {})
            api_key = vt_config.get('api_key')
            api_url = vt_config.get('api_url')
            threshold = vt_config.get('malicious_threshold', 1)
            
            if not api_key or api_key == "YOUR_API_KEY_HERE":
                print(f"URLFilter: No VirusTotal API key, using local check for {url}")
                return await self.check_url_local(url)
            
            # Ensure URL has protocol for VirusTotal
            check_url = url if url.startswith(('http://', 'https://')) else f'http://{url}'
            
            params = {
                'apikey': api_key,
                'resource': check_url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        if result.get('response_code') == 1:
                            positives = result.get('positives', 0)
                            total = result.get('total', 0)
                            
                            # Get categories from VirusTotal response
                            categories = result.get('categories', [])
                            print(f"URLFilter: VirusTotal categories for {url}: {categories}")
                            category = self.determine_category_from_vt(url, categories)
                            
                            print(f"URLFilter: VirusTotal scan - {positives}/{total} engines flagged {url}")
                            print(f"URLFilter: Categorized {url} as {category}")
                            
                            if positives >= threshold:
                                print(f"URLFilter: VirusTotal BLOCKING {url} - {positives} detections")
                                return 'blocked', 'malicious'
                            else:
                                print(f"URLFilter: VirusTotal ALLOWING {url} - {positives} detections")
                                return 'safe', category
                        else:
                            print(f"URLFilter: VirusTotal - URL not found in database, using local check")
                            return await self.check_url_local(url)
                    else:
                        print(f"URLFilter: VirusTotal API error {response.status}, using local check")
                        return await self.check_url_local(url)
                        
        except Exception as e:
            print(f"URLFilter: VirusTotal error: {e}, using local check")
            return await self.check_url_local(url)
    
    def determine_category_from_vt(self, url: str, vt_categories: List[str]) -> str:
        """Use only the first category from VirusTotal response"""
        if vt_categories:
            print(f"URLFilter: VirusTotal categories: {vt_categories}")
            # Use only the first category from VirusTotal
            category = vt_categories[0].lower().replace(' ', '_')
            print(f"URLFilter: Using VirusTotal category: {category}")
            return category
        
        return 'unknown'
    
    async def check_url_local(self, url: str) -> tuple[str, str]:
        """Local URL checking as fallback - returns (status, category)"""
        domain = self.extract_domain(url)
        
        # Check trusted domains from dlp_rules.json structure
        trusted_domains = self.reputation_data.get('url_filtering', {}).get('trusted_domains', [])
        if domain in trusted_domains:
            print(f"URLFilter: Categorized {url} as tech (trusted domain)")
            return 'safe', 'tech'
        
        # Check categories (fallback structure)
        for category, domains in self.reputation_data.get('categories', {}).items():
            if domain in domains:
                print(f"URLFilter: Categorized {url} as {category}")
                return 'safe', category
        
        print(f"URLFilter: Unknown URL {url} - allowing")
        return 'safe', 'unknown'
    
    def extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        # Handle full URLs
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        if match:
            return match.group(1)
        
        # Handle domain-only URLs
        domain_match = re.search(r'(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})', url)
        if domain_match:
            return domain_match.group(1)
        
        return url
    
    async def process_message_urls(self, text: str, nick: str, room: str) -> tuple[str, bool]:
        """Process URLs in message text, return (processed_text, is_blocked)"""
        urls = self.extract_urls(text)
        
        if not urls:
            return text, False
        
        print(f"URLFilter: Found {len(urls)} URL(s) in message from {nick}")
        
        processed_text = text
        for url in urls:
            status, category = await self.check_url_with_virustotal(url)
            
            if status == 'blocked':
                print(f"URLFilter: BLOCKING malicious URL: {url}")
                return text, True
            else:
                # Add category info to the message for user visibility
                category_info = f" [🔗 {category.upper()}]" if category != 'unknown' else " [🔗 LINK]"
                processed_text = processed_text.replace(url, url + category_info)
        
        return processed_text, False