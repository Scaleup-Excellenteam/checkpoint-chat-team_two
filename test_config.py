#!/usr/bin/env python3
from server.config import settings

print("Configuration Test:")
print(f"Host: {settings.host}")
print(f"Port: {settings.port}")
print(f"Default Room: {settings.default_room}")
print(f"DLP Enabled: {settings.enable_dlp}")
print(f"Log Level: {settings.log_level}")
print(f"Environment: {settings.environment}")
print(f"Gemini API Key: {settings.gemini_api_key}")