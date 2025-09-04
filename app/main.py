from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import endpoints, auth
from app.database import Base, engine
from app.core.config import settings

# from auth import auth

Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(endpoints.router)
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Robust Architecture Generator API v2.0",
        "features": [
            "Project analysis and context extraction",
            "Dynamic clarification questions",
            "ReactFlow architecture diagrams",
            "Database schema diagrams",
            "Detailed text architecture documents",
        ],
        "available_icons": settings.AVAILABLE_ICONS,
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.PROJECT_VERSION,
    }

@app.get("/icons")
async def get_available_icons():
    """Return list of available icons for frontend"""
    return {"icons": settings.AVAILABLE_ICONS}