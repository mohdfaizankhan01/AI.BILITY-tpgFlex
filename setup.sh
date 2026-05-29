#!/bin/bash
# tpgFlex Voice Booking – one-command setup
# Run from project root: bash setup.sh

echo "📦 Installing dependencies..."
pip install -r requirements.txt -q

echo "🗄️  Seeding mock database..."
cd backend
python -m mock_data.seed
cd ..

echo ""
echo "✅ Setup complete. Now run:"
echo ""
echo "  1) Start backend:   uvicorn backend.main:app --reload --port 8000"
echo "  2) Open frontend:   open frontend/index.html"
echo ""
echo "API docs at: http://localhost:8000/docs"
