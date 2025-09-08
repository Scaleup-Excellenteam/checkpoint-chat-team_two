from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import re
import json
from security.dlp_handler import DLPHandler
from security.url_filter import URLFilter

# Responsible for processing messages through various handlers

class MessageHandler(ABC):
    # Strategy Pattern - all handlers must have a process method - ValidationHandler, DLPHandler, URLFilter
    @abstractmethod
    async def process(self, message: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process message, return None to block"""
        pass

class ValidationHandler(MessageHandler):
    async def process(self, message, context):
        # Basic validation
        if not message.get('text') or len(message['text']) > 1024:
            return None
        if not message.get('room') or not message.get('nick'):
            return None
        
        text_lower = message['text'].lower()
        if 'pineapple' in text_lower:
            # TODO: Block the message entirely
            return None
        
        return message

class DLPMessageHandler(MessageHandler):
    def __init__(self, dlp_handler: DLPHandler, use_gemini: bool = False):
        self.dlp_handler = dlp_handler
        self.use_gemini = use_gemini
    
    async def process(self, message, context):
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
        
        if is_blocked:
            return None
        
        message['text'] = processed_text
        return message

class URLFilterHandler(MessageHandler):
    def __init__(self, url_filter: URLFilter):
        self.url_filter = url_filter
    
    async def process(self, message, context):
        print(f"URLFilterHandler: Processing message from {message['nick']}: {message['text']}")
        
        processed_text, is_blocked = await self.url_filter.process_message_urls(
            message['text'],
            message['nick'],
            message['room']
        )
        
        if is_blocked:
            print(f"URLFilterHandler: BLOCKED message from {message['nick']} due to malicious URL")
            return None
        
        print(f"URLFilterHandler: ALLOWED message from {message['nick']}")
        message['text'] = processed_text
        return message

class MessagePipeline:
    def __init__(self):
        self.handlers = []
    
    async def process(self, raw_message: str, websocket) -> Optional[str]:
        # Parse wire format to dict
        message = self.parse_message(raw_message)
        if not message:
            return None
            
        context = {'websocket': websocket, 'raw': raw_message}
        
        # Run through handlers
        for handler in self.handlers:
            message = await handler.process(message, context)
            if message is None:
                return None
        
        # Convert back to wire format
        return self.serialize_message(message)
    
    def parse_message(self, raw: str) -> Optional[Dict]:
        # Parse your room|nick|text format
        match = re.match(r"^([^|]{1,64})\|([^|]{1,64})\|(.*)$", raw)
        if match:
            room, nick, text = match.groups()
            return {'room': room, 'nick': nick, 'text': text}
        return None
    
    def serialize_message(self, msg: Dict) -> str:
        return f"{msg['room']}|{msg['nick']}|{msg['text']}"