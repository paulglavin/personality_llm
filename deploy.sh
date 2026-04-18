#!/bin/bash

# Deploy personality_llm to Home Assistant
HA_HOST="192.168.2.30"
HA_USER="root"
HA_PATH="/config/custom_components/personality_llm"
LOCAL_PATH="./custom_components/personality_llm"

echo "Deploying personality_llm to Home Assistant..."

scp -r "$LOCAL_PATH" "$HA_USER@$HA_HOST:$HA_PATH"

echo "Done. Restart Home Assistant to pick up changes."