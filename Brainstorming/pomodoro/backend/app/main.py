"""FastAPI application entry point for Deep Focus."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, distractions, profile, sessions, tags

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Deep Focus API",
    description="Pomodoro Reimagined — gamified focus tracking backend",
    version="1.0.0",
)

# CORS — allow all origins in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(tags.router)
app.include_router(distractions.router)
app.include_router(profile.router)


@app.get("/")
def aroot():
    return {"message": "Deep Focus API is running"}
