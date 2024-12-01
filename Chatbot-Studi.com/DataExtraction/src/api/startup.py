from api.config import create_app
from web_services.rag_query_controller import router

app = create_app()

# Include the router for API endpoints
app.include_router(router)