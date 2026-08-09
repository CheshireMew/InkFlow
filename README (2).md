# InkFlow

AI-powered writing workflow engine.

Current architecture:
- Recipes describe a stateless workflow contract.
- Frontend owns step state and local review.
- Backend executes server-side steps and applies a unified writing contract for LLM generation.

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
- `POST /api/actions/run` - Execute a single server-side step

## Project Structure

```
InkFlow/
├── backend/
│   ├── main.py           # FastAPI app
│   ├── steps/            # Step implementations
│   ├── recipes/          # Recipe loader
│   ├── services/         # LLM, HTTP, etc.
│   ├── core/            # Workflow and writing contracts
│   └── routers/          # API routes
├── recipes/              # YAML recipes
│   ├── social/           # Twitter, etc.
│   ├── marketing/        # Ads, copy
│   └── learning/         # Tutorials
└── frontend/             # React app
```
