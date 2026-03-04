#!/bin/bash
echo "Starting Deep Care Voice Gateway..."

# Activate virtual environment if it exists
if [ -d ".env" ]; then
    source .env/bin/activate
fi

# Run the server
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
