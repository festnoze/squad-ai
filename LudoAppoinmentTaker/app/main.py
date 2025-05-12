import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from endpoints import router as api_router

# Configure logging for the entire application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Set up project paths
project_root = os.path.dirname(os.path.dirname(__file__))

# Configure Google Calendar credentials
google_calendar_credentials_filename = os.getenv(
    "GOOGLE_CALENDAR_CREDENTIALS_FILENAME", 
    "secrets/google-calendar-credentials.json"
)
google_calendar_credentials_path = os.path.join(project_root, google_calendar_credentials_filename)
print(google_calendar_credentials_path)

if os.path.exists(google_calendar_credentials_path):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = google_calendar_credentials_path
    logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {google_calendar_credentials_path}")
else:
    logger.warning(f"/!\\ Warning: Google calendar credentials file not found at {google_calendar_credentials_path}")

# Create FastAPI application
app = FastAPI(
    title="Ludo Appointment Taker",
    description="FastAPI application for handling Twilio voice calls and booking appointments",
    version="1.0.0"
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
    )

@app.on_event("startup")
def startup_event():
    """Initialize components on application startup"""
    logger.info("Starting Ludo Appointment Taker application")
    
    # Create static directory if it doesn't exist
    os.makedirs("static/audio", exist_ok=True)
    
@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down Ludo Appointment Taker application")
    # Add any cleanup logic here if needed