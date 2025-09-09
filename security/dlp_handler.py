import re
import json
import asyncio
import aiohttp
from typing import Dict, List, Optional
from message_pipline import MessageHandler

# Responsible for Data Loss Prevention (DLP) handling, URL filtering, and redaction

class DLPHandler:
    def __init__(self, config_path: str = "config/dlp_rules.json"):
        with open(config_path) as f:
            self.config = json.load(f)
            
    def check_message(self, text: str, room: str) -> tuple[str, bool]:
        """Returns (processed_text, is_blocked)"""
        print(f"DLPHandler: Checking message '{text}' for recipe keywords")
        # Quick keyword check first
        for keyword in self.config.get('recipe_keywords', []):
            if keyword.lower() in text.lower():
                print(f"DLPHandler: FOUND keyword '{keyword}' in message - BLOCKING")
                return text, True
        
        print(f"DLPHandler: No recipe keywords found - ALLOWING")
        return text, False
    
    def _is_safe_message(self, text: str) -> bool:
        """Check if message is clearly safe and doesn't need Gemini analysis"""
        text_lower = text.lower().strip()
        
        # Check safe patterns
        for pattern in self.config.get('safe_patterns', []):
            if re.search(pattern, text_lower):
                return True
        
        # Very short messages are usually safe
        if len(text_lower) < 10:
            return True
            
        return False

    def _is_suspicious(self, text: str) -> bool:
        """Check if message contains suspicious indicators that warrant Gemini analysis"""
        text_lower = text.lower()
        
        # Check for suspicious indicators
        for indicator in self.config.get('suspicious_indicators', []):
            if indicator in text_lower:
                return True
        
        return False
    
    async def check_message_async(self, text: str, room: str) -> tuple[str, bool]:
        """Async version with smart Gemini filtering"""
        print(f"DLPHandler: Async checking message '{text}' for recipe keywords")
        # First check keywords (immediate block)
        for keyword in self.config.get('recipe_keywords', []):
            if keyword.lower() in text.lower():
                print(f"DLPHandler: FOUND keyword '{keyword}' in message - BLOCKING")
                return text, True
        
        # Check if message is clearly safe
        if self._is_safe_message(text):
            return text, False  # Allow without Gemini check
        
        # Check if message is suspicious enough for Gemini
        if self._is_suspicious(text):
            gemini_result = await self._check_with_gemini(text)
            if gemini_result == "BLOCK":
                return text, True
        
        # Default: allow message
        return text, False
    
    async def _check_with_gemini(self, text: str) -> Optional[str]:
        """Send message to Gemini API for analysis"""
        try:
            gemini_config = self.config.get('gemini_config', {})
            api_key = gemini_config.get('api_key')
            api_url = gemini_config.get('api_url')
            prompt = gemini_config.get('prompt_template', '').format(message=text)
            
            if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                return "ALLOW"  # No API key configured
            
            headers = {
                'Content-Type': 'application/json',
            }
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{api_url}?key={api_key}",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Extract response text
                        candidates = result.get('candidates', [])
                        if candidates:
                            content = candidates[0].get('content', {})
                            parts = content.get('parts', [])
                            if parts:
                                response_text = parts[0].get('text', '').strip().upper()
                                return "BLOCK" if "BLOCK" in response_text else "ALLOW"
                    
                    return "ALLOW"  # Default on API error
                
        except Exception as e:
            print(f"Gemini API error: {e}")
            return "ALLOW"  # Default to allow on API failure

class DLPMessageHandler(MessageHandler):
    def __init__(self, dlp_handler: 'DLPHandler', use_gemini: bool = False):
        self.dlp_handler = dlp_handler
        self.use_gemini = use_gemini
    
    async def process(self, message, context):
        print(f"DLPMessageHandler: Processing message: {message}")
        if self.use_gemini:
            processed_text, is_blocked = await self.dlp_handler.check_message_async(
                message['text'], 
                message['room']
            )
        else:
            processed_text, is_blocked = self.dlp_handler.check_message(
                message['text'], 
                message['room']
            )
        
        print(f"DLPMessageHandler: is_blocked={is_blocked}, text='{message['text']}'")
        if is_blocked:
            print(f"DLPMessageHandler: BLOCKING message")
            return None
        
        message['text'] = processed_text
        return message