#!/usr/bin/env python3
"""Create .env.example file from template."""

from src.config.settings import ENV_TEMPLATE

with open('.env.example', 'w') as f:
    f.write(ENV_TEMPLATE)

print(".env.example file created successfully!")
print("Copy it to .env and update with your configuration.") 