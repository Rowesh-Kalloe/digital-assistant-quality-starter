from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
from loguru import logger

from app.routers import chat, health, enhanced_chat, enhanced_chat_with_validation
from app.services.openai_service import OpenAIService
from app.services.enhanced_openai_service import EnhancedOpenAIService
from app.services.n8n_validation_service import N8NValidationService

# Load environment variables
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("Starting Gemeente AI Assistant API with N8N Validation")
    
    # Initialize services
    try:
        # Legacy service for backwards compatibility
        openai_service = OpenAIService()
        app.state.openai_service = openai_service
        logger.info("✓ Legacy OpenAI service initialized successfully")
        
        # Enhanced service with structured outputs
        enhanced_openai_service = EnhancedOpenAIService()
        app.state.enhanced_openai_service = enhanced_openai_service
        logger.info("✓ Enhanced OpenAI service initialized successfully")
        
        # N8N validation service for security layer
        n8n_validation_service = N8NValidationService()
        app.state.n8n_validation_service = n8n_validation_service
        
        if n8n_validation_service.enabled:
            logger.info(f"✓ N8N validation service initialized and ENABLED")
            logger.info(f"  Webhook URL: {n8n_validation_service.webhook_url}")
            logger.info(f"  Timeout: {n8n_validation_service.validation_timeout}s")
        else:
            logger.info("✓ N8N validation service initialized but DISABLED")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    logger.info("Shutting down Gemeente AI Assistant API")

# Create FastAPI application
app = FastAPI(
    title="Gemeente AI Assistant API with N8N Validation",
    description="AI-powered assistant for Dutch municipal digital transformation with advanced security validation layer",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") != "production" else None
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://127.0.0.1:3000",
        "https://gemeente-ai.nl",  # Production domain
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(enhanced_chat.router, prefix="/api", tags=["enhanced-chat"])
app.include_router(enhanced_chat_with_validation.router, prefix="/api", tags=["validated-chat"])

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for better error responses"""
    logger.exception(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Er ging iets mis op de server. Probeer het later opnieuw.",
            "needsHumanHelp": True
        }
    )

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Gemeente AI Assistant API with N8N Validation", 
        "status": "active",
        "version": "1.1.0",
        "n8n_validation": os.getenv("N8N_VALIDATION_ENABLED", "false")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_with_n8n:app",
        host="0.0.0.0",
        port=8000,
        reload=True if os.getenv("ENVIRONMENT") != "production" else False,
        log_level="info"
    )
