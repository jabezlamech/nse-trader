#!/bin/bash
# NSE Candle Analyzer - Start Script
echo "Starting NSE Candle Analyzer..."
echo "Dashboard: http://localhost:8000"
echo "API Docs:  http://localhost:8000/docs"
echo ""
cd "$(dirname "$0")/backend"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
