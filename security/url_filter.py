import re
import json
import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Responsible for URL filtering using VirusTotal and Klazify

class URLFilter:
    def __init__(self, config_path: str = "config/dlp_rules.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        
        # Setup logging
        import os
        os.makedirs('logs', exist_ok=True)
        
        self.logger = logging.getLogger('url_filter')
        if not self.logger.handlers:  # Avoid duplicate handlers
            handler = logging.FileHandler('logs/url_analysis.log')
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        print("URL Filter initialized with logging to logs/url_analysis.log")
    
    def extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text"""
        # Pattern for URLs with http/https
        http_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        # Pattern for domain-only URLs (like one.co.il)
        domain_pattern = r'\b[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?\b'
        
        urls = []
        # Find HTTP/HTTPS URLs
        urls.extend(re.findall(http_pattern, text, re.IGNORECASE))
        
        # Find domain-only URLs and add http:// prefix
        domain_matches = re.findall(domain_pattern, text)
        for match in domain_matches:
            full_match = re.search(r'\b[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?\b', text)
            if full_match:
                domain = full_match.group()
                if not any(domain in url for url in urls):  # Avoid duplicates
                    urls.append(f"http://{domain}")
        
        return urls
    
    def is_trusted_domain(self, url: str) -> bool:
        """Check if URL is from trusted domain"""
        trusted_domains = self.config.get('url_filtering', {}).get('trusted_domains', [])
        for domain in trusted_domains:
            if domain in url.lower():
                return True
        return False
    
    async def check_virustotal(self, url: str) -> Dict:
        """Check URL with VirusTotal API for malicious detection and category"""
        try:
            vt_config = self.config.get('url_filtering', {}).get('virustotal', {})
            api_key = vt_config.get('api_key')
            api_url = vt_config.get('api_url')
            
            if not api_key or api_key == "YOUR_VT_API_KEY":
                return {"status": "no_api_key", "malicious": False, "positives": 0, "total": 0, "category": "Unknown"}
            
            params = {
                'apikey': api_key,
                'resource': url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        positives = result.get('positives', 0)
                        total = result.get('total', 0)
                        threshold = vt_config.get('malicious_threshold', 1)
                        
                        # Extract category from VirusTotal response
                        category = self._extract_category_from_vt(result)
                        
                        return {
                            "status": "success",
                            "malicious": positives >= threshold,
                            "positives": positives,
                            "total": total,
                            "scan_date": result.get('scan_date', 'unknown'),
                            "category": category
                        }
                    else:
                        return {"status": "api_error", "malicious": False, "positives": 0, "total": 0, "category": "Unknown"}
        
        except Exception as e:
            self.logger.error(f"VirusTotal API error: {e}")
            return {"status": "error", "malicious": False, "positives": 0, "total": 0, "category": "Unknown"}
    

    
    def _extract_category_from_vt(self, vt_response: Dict) -> str:
        """Extract category information from VirusTotal response"""
        # VirusTotal provides categories in different fields
        categories = vt_response.get('categories', [])
        if categories:
            return categories[0] if isinstance(categories, list) else str(categories)
        
        # Check for Webutation categories
        webutation = vt_response.get('Webutation domain info', {})
        if webutation and 'Categories' in webutation:
            cats = webutation['Categories']
            if cats:
                return cats[0] if isinstance(cats, list) else str(cats)
        
        # Check scans for category hints
        scans = vt_response.get('scans', {})
        for scanner, result in scans.items():
            if result.get('detected') and 'category' in result.get('result', '').lower():
                return result.get('result', 'Unknown')
        
        # Fallback: try to determine from URL structure
        return self._guess_category_from_url(vt_response.get('url', ''))
    
    def _guess_category_from_url(self, url: str) -> str:
        """Guess category from URL patterns and known domains"""
        url_lower = url.lower()
        
        # Sports domains and keywords
        sports_domains = ['one.co.il', 'sport5.co.il', 'ynet.co.il/sport', 'espn.com', 'sport.walla.co.il']
        sports_keywords = ['sport', 'football', 'basketball', 'soccer', 'tennis', 'baseball', 'hockey']
        
        # News domains and keywords  
        news_domains = ['cnn.com', 'bbc.com', 'reuters.com', 'ynet.co.il', 'haaretz.co.il', 'mako.co.il']
        news_keywords = ['news', 'breaking', 'politics', 'world']
        
        # Technology domains and keywords
        tech_domains = ['github.com', 'stackoverflow.com', 'techcrunch.com', 'wired.com']
        tech_keywords = ['tech', 'programming', 'software', 'code']
        
        # Shopping domains and keywords
        shopping_domains = ['amazon.com', 'ebay.com', 'aliexpress.com', 'zap.co.il']
        shopping_keywords = ['shop', 'store', 'buy', 'sale', 'price']
        
        # Social media domains
        social_domains = ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'tiktok.com']
        
        # Gaming domains and keywords
        gaming_domains = ['steam.com', 'twitch.tv', 'ign.com']
        gaming_keywords = ['game', 'gaming', 'play', 'xbox', 'playstation']
        
        # Check domains first (more accurate)
        if any(domain in url_lower for domain in sports_domains):
            return 'Sports'
        elif any(domain in url_lower for domain in news_domains):
            return 'News & Media'
        elif any(domain in url_lower for domain in tech_domains):
            return 'Technology'
        elif any(domain in url_lower for domain in shopping_domains):
            return 'Shopping'
        elif any(domain in url_lower for domain in social_domains):
            return 'Social Media'
        elif any(domain in url_lower for domain in gaming_domains):
            return 'Gaming'
        
        # Check keywords if domain not recognized
        elif any(word in url_lower for word in sports_keywords):
            return 'Sports'
        elif any(word in url_lower for word in news_keywords):
            return 'News & Media'
        elif any(word in url_lower for word in tech_keywords):
            return 'Technology'
        elif any(word in url_lower for word in shopping_keywords):
            return 'Shopping'
        elif any(word in url_lower for word in gaming_keywords):
            return 'Gaming'
        else:
            return 'General'
    
    def log_url_analysis(self, url: str, user: str, room: str, vt_result: Dict, action: str):
        """Log URL analysis results"""
        log_entry = f"""URL Analysis:
  User: {user} | Room: {room} | Action: {action}
  URL: {url}
  VirusTotal: {'MALICIOUS' if vt_result.get('malicious') else 'SAFE'} ({vt_result.get('positives', 0)}/{vt_result.get('total', 0)} engines flagged)
  Category: {vt_result.get('category', 'Unknown')}
  Scan Date: {vt_result.get('scan_date', 'Unknown')}
"""
        self.logger.info(log_entry)
    
    async def process_message_urls(self, text: str, user: str, room: str) -> Tuple[str, bool]:
        """Process all URLs in message. Returns (processed_text, is_blocked)"""
        urls = self.extract_urls(text)
        
        print(f"URLFilter: Found {len(urls)} URLs in message: {urls}")
        
        if not urls:
            print(f"URLFilter: No URLs found in message: {text}")
            return text, False
        
        for url in urls:
            print(f"URLFilter: Processing URL: {url}")
            # Skip trusted domains but still categorize
            if self.is_trusted_domain(url):
                category = self._guess_category_from_url(url)
                print(f"URLFilter: {url} is TRUSTED domain, category: {category}")
                self.log_url_analysis(url, user, room, 
                                    {"malicious": False, "positives": 0, "total": 0, "scan_date": "trusted", "category": category}, 
                                    "ALLOWED_TRUSTED")
                continue
            
            # Check with VirusTotal
            print(f"URLFilter: Checking {url} with VirusTotal...")
            vt_result = await self.check_virustotal(url)
            print(f"URLFilter: VirusTotal result for {url}: {vt_result}")
            
            if vt_result.get('malicious', False):
                # Block message if malicious URL found
                print(f"URLFilter: BLOCKING message due to malicious URL: {url}")
                self.log_url_analysis(url, user, room, vt_result, "BLOCKED")
                return text, True
            else:
                # Log safe URL
                print(f"URLFilter: ALLOWING URL: {url}, category: {vt_result.get('category', 'Unknown')}")
                self.log_url_analysis(url, user, room, vt_result, "ALLOWED")
        
        return text, False