#!/bin/bash

# Always recreate .env from example
echo "Creating .env file from .env.example..."
cp .env.example .env
echo "✅ .env file created successfully!"
echo "📝 Please review and modify .env file if needed"
