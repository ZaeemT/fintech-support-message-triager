from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from .core.config import get_settings
from .database import database
from .core.exceptions import BaseAPIException, NotFoundException, BadRequestException, DatabaseException
from .core.responses import ErrorResponse, ServiceResponse
from .modules.users.controller import router as user_router
from .modules.auth.controller import router as auth_router
from .modules.triage.controller import router as triage_router
from .integrations.jev import create_jev_client
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager to handle startup and shutdown events.
    Connects to the database and creates the shared Jev client on startup; closes both on shutdown.
    """
    await database.connect_to_mongodb()
    app.state.jev_client = create_jev_client()
    yield
    await app.state.jev_client.aclose()
    await database.close_mongodb_connection()


app = FastAPI(
    title=get_settings().APP_NAME,
    version=get_settings().APP_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development; adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(BaseAPIException)
async def base_api_exception_handler(request, exc: BaseAPIException):
    """Custom exception handler for all BaseAPIException errors."""
    error_response = ErrorResponse(
        message=exc.message,
        status_code=exc.status_code
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump()
    )

# app.include_router(user_router, prefix="/v1/users", tags=["users"])
# app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
app.include_router(triage_router, prefix="/v1/triage", tags=["triage"])


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "FastAPI MongoDB App is running!"}

@app.get("/health")
async def health_check():
    """Health check with database status"""
    try:
        # Simple check if database is connected
        if database.db is not None:
            return {"status": "healthy", "database": "connected"}
        else:
            return {"status": "unhealthy", "database": "disconnected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

