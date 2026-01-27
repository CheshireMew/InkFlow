"""
InkFlow Backend - Main Application

FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file before other imports
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from steps import discover_steps
from recipes.loader import init_recipe_loader
from services.http_client import close_http_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("InkFlow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("🚀 Starting InkFlow Backend...")
    
    # Discover and register all steps
    discover_steps()
    
    # Load recipes
    recipes_dir = Path(__file__).parent.parent / "recipes"
    init_recipe_loader(recipes_dir)
    
    logger.info("✅ InkFlow Backend ready")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down InkFlow Backend...")
    await close_http_client()
    logger.info("👋 Goodbye!")


# Create FastAPI app
app = FastAPI(
    title="InkFlow API",
    description="AI-powered writing workflow engine",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "inkflow"}


# Import and include routers
from routers import recipes, pipelines, actions

app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
app.include_router(pipelines.router, prefix="/api/pipelines", tags=["pipelines"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
