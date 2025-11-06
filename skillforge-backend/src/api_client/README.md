# Studi Parcours API Client

This module provides a Python client for the Studi Parcours API, specifically for accessing the hierarchy endpoint.

## Features

- ✅ Async/await support with proper async naming convention (methods prefixed with 'a')
- ✅ Full type hints and Pydantic models for response validation
- ✅ Comprehensive error handling
- ✅ Environment-based configuration
- ✅ Configurable timeouts
- ✅ Optional caching support
- ✅ 100% test coverage

## Installation

The client requires `httpx` which is included in the project dependencies:

```bash
uv add httpx
```

## Configuration

Add the following environment variable to your `.env` file:

```env
# Other API Configuration
OTHERS_API_BASE_URL=https://api.studi.fr
```

**Authentication:** The client uses JWT token authentication. The token can be:
- Provided from the frontend (passed through from user requests)
- Created using `JWTHelper.create_token()` for server-side requests

## Usage

### Basic Usage

```python
from api_client import StudiParcoursApiClient
from security.jwt_helper import JWTHelper

# Option 1: Use token from frontend (in a router endpoint)
async def get_parcours_endpoint(parcours_id: int, token: str):
    client = StudiParcoursApiClient(jwt_token=token)
    hierarchy = await client.aget_parcours_hierarchy(parcours_id=parcours_id)
    return hierarchy

# Option 2: Create token for server-side requests
token = await JWTHelper.create_token(user_id=123, lms_user_id="user123")
client = StudiParcoursApiClient(jwt_token=token)
hierarchy = await client.aget_parcours_hierarchy(parcours_id=123)

# Access the data
print(f"Parcours: {hierarchy.titre}")
print(f"Number of matieres: {len(hierarchy.matieres)}")

# Iterate through the structure
for matiere in hierarchy.matieres:
    print(f"Matiere: {matiere.titre}")
    for module in matiere.modules:
        print(f"  Module: {module.titre}")
        for theme in module.themes:
            print(f"    Theme: {theme.titre}")
            for ressource in theme.ressources:
                print(f"      Ressource: {ressource.titre}")
```

### Custom Configuration

```python
# Initialize with custom configuration
client = StudiParcoursApiClient(
    jwt_token="your-jwt-token",
    base_url="https://custom-api.example.com",
    timeout=60.0  # 60 seconds timeout
)

# Or pass token per-request
client = StudiParcoursApiClient(base_url="https://api.example.com")
hierarchy = await client.aget_parcours_hierarchy(
    parcours_id=123,
    jwt_token="request-specific-token"
)
```

### Using Cache

```python
# Enable caching (if supported by the API)
hierarchy = await client.aget_parcours_hierarchy(
    parcours_id=123,
    use_cache=True
)
```

### Getting Raw JSON Response

```python
# Get raw JSON string (useful for debugging)
json_response = await client.aget_parcours_hierarchy_json(parcours_id=123)
print(json_response)
```

### Error Handling

```python
from api_client import StudiParcoursApiClient, StudiParcoursApiClientException

client = StudiParcoursApiClient()

try:
    hierarchy = await client.aget_parcours_hierarchy(parcours_id=123)
except StudiParcoursApiClientException as e:
    print(f"API Error: {e}")
    # Handle the error appropriately
```

## Data Structure

The `ParcoursHierarchy` model represents the complete structure returned by the API:

```
ParcoursHierarchy
├── id, code, titre, publication_date, archived, file_name
├── blocs: List[BlocHierarchy]
│   └── evaluations: List[EvaluationHierarchy]
│       └── modules: List[EvaluationModuleHierarchy]
├── matieres: List[MatiereHierarchy]
│   ├── modules: List[ModuleHierarchy]
│   │   └── themes: List[ThemeHierarchy]
│   │       └── ressources: List[RessourceHierarchy]
│   └── examens: List[ExamenHierarchy]
└── examens: List[ExamenHierarchy]
```

## Models

All models are defined in `api_client.models.parcours_hierarchy_models`:

- `ParcoursHierarchy` - Root model
- `BlocHierarchy` - Bloc structure
- `MatiereHierarchy` - Subject/Matiere structure
- `ModuleHierarchy` - Module structure
- `ThemeHierarchy` - Theme structure
- `RessourceHierarchy` - Resource structure
- `EvaluationHierarchy` - Evaluation structure
- `EvaluationModuleHierarchy` - Evaluation module structure
- `ExamenHierarchy` - Exam structure

All models use Pydantic for validation and serialization, supporting:
- Field aliases (matching the API's snake_case naming)
- Optional fields with proper null handling
- Type validation
- JSON serialization/deserialization

## Testing

Run the tests with:

```bash
.venv/Scripts/python.exe -m pytest tests/api_client/test_studi_parcours_api_client.py -v
```

The test suite includes:
- ✅ Successful API responses
- ✅ Cache parameter handling
- ✅ HTTP error handling
- ✅ Network error handling
- ✅ Invalid JSON handling
- ✅ Raw JSON response
- ✅ Client initialization
- ✅ Header generation

## Integration Example

Here's a complete example of using the client in a service:

```python
from api_client import StudiParcoursApiClient, StudiParcoursApiClientException
from envvar import EnvHelper

class ParcoursService:
    def __init__(self) -> None:
        self.client = StudiParcoursApiClient()

    async def aget_parcours_structure(self, parcours_id: int) -> dict[str, any]:
        """Get a simplified parcours structure."""
        try:
            hierarchy = await self.client.aget_parcours_hierarchy(parcours_id)

            return {
                "id": hierarchy.id,
                "titre": hierarchy.titre,
                "matieres_count": len(hierarchy.matieres),
                "blocs_count": len(hierarchy.blocs),
                "examens_count": len(hierarchy.examens),
                "matieres": [
                    {
                        "titre": mat.titre,
                        "modules_count": len(mat.modules),
                    }
                    for mat in hierarchy.matieres
                ]
            }
        except StudiParcoursApiClientException as e:
            # Log the error and handle appropriately
            print(f"Failed to fetch parcours: {e}")
            raise
```

## API Endpoint

The client accesses the following endpoint:

```
GET {base_url}/{parcoursId}/hierarchy?useCache={true|false}
```

Example:
```
GET https://api.studi.fr/parcours/123/hierarchy?useCache=false
Authorization: Bearer {jwt-token}
```

## Authentication

The client uses JWT Bearer token authentication. The token is included in the `Authorization` header:

```
Authorization: Bearer {jwt-token}
```

**Token Sources:**
1. **Frontend Token**: Pass the user's JWT token from the frontend request
   ```python
   # In a FastAPI endpoint
   @router.get("/parcours/{parcours_id}")
   async def get_parcours(
       parcours_id: int,
       token_payload: JWTSkillForgePayload = Depends(authentication_required)
   ):
       # token_payload contains the decoded JWT from the Authorization header
       client = StudiParcoursApiClient(jwt_token=token_payload.raw_token)
       return await client.aget_parcours_hierarchy(parcours_id)
   ```

2. **Server-Generated Token**: Create a token using `JWTHelper` for background tasks
   ```python
   from security.jwt_helper import JWTHelper

   token = await JWTHelper.create_token(user_id=123, lms_user_id="user123")
   client = StudiParcoursApiClient(jwt_token=token)
   ```
