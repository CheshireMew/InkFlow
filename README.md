# InkFlow

AI-powered writing workflow engine.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Set API key
export DEEPSEEK_API_KEY="your-api-key"

# Run server
cd backend
python main.py
```

cd backend; python main.py

cd frontend; npm run dev

## API Endpoints

- `GET /health` - Health check
- `GET /api/recipes` - List recipes
- `GET /api/recipes/{id}` - Get recipe details
- `POST /api/pipelines/create` - Create pipeline
- `POST /api/pipelines/execute` - Execute step

## Project Structure

```
InkFlow/
├── backend/
│   ├── main.py           # FastAPI app
│   ├── steps/            # Step implementations
│   ├── recipes/          # Recipe loader
│   ├── services/         # LLM, HTTP, etc.
│   └── routers/          # API routes
├── recipes/              # YAML recipes
│   ├── social/           # Twitter, etc.
│   ├── marketing/        # Ads, copy
│   └── learning/         # Tutorials
└── frontend/             # React app (WIP)
```
