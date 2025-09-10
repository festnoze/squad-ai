"""FastAPI main application for Turtle Trading Bot."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.routers import charts, strategies, trading, portfolio, market_data
from app.core.config import settings

# Create FastAPI app
app = FastAPI(
    title="Turtle Trading Bot API",
    description="A comprehensive trading bot API implementing the Turtle Trading methodology",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Add middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(charts.router, prefix="/api/charts", tags=["charts"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(trading.router, prefix="/api/trading", tags=["trading"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["market-data"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Turtle Trading Bot API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )