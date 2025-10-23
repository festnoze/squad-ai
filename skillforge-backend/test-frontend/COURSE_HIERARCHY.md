# Course Hierarchy Reference

## Data Structure

The course hierarchy in SkillForge follows this exact structure from the backend:

```
CourseContent (Parcours)
│
├── parcours_id           ← Unique ID
├── parcours_code         ← Code reference
├── name                  ← Display name
├── is_demo               ← Demo flag
├── start_date            ← Course dates
├── end_date
├── promotion_name        ← Cohort info
├── promotion_id
│
└── Collections:
    ├── matieres[]                    (Subjects)
    │   ├── matiere_id
    │   ├── name
    │   ├── code
    │   └── modules[] ──────┐
    │                        │
    ├── modules[]            ├────────(Modules)
    │   ├── module_id        │
    │   ├── name             │
    │   ├── code             │
    │   ├── matiere ←────────┘ (parent reference)
    │   └── themes[] ───────┐
    │                        │
    ├── themes[]             ├────────(Themes)
    │   ├── theme_id         │
    │   ├── name             │
    │   ├── code             │
    │   ├── module ←─────────┘ (parent reference)
    │   └── ressources[] ───┐
    │                        │
    ├── ressources[]         ├────────(Resources)
    │   ├── ressource_id     │
    │   ├── name             │
    │   ├── code             │
    │   ├── theme ←──────────┘ (parent reference)
    │   └── ressource_objects[] ──┐
    │                              │
    └── ressource_objects[]        ├─(Resource Objects)
        ├── ressource_object_id    │
        ├── name                   │
        ├── type (pdf/opale)       │
        ├── url                    │
        ├── ressource ←────────────┘ (parent reference)
        └── hierarchy
            ├── ressource ←─── (full hierarchy context)
            ├── theme
            ├── module
            └── matiere
```

## Navigation Flow in chatbot.py

### Frontend Display Order:
```
1. CourseContent Selection
   ↓
2. Matiere Selection (dropdown)
   ↓
3. Module Selection (dropdown)
   ↓
4. Theme Selection (dropdown)
   ↓
5. RessourceObject Selection (dropdown)
   ↓
6. Display URL in iframe + Enable chat
```

### Backend Context for API:
```python
{
    "ressource": {
        "ressource_id": ro.id,
        "ressource_type": ro.type,  # "pdf" or "opale"
        "ressource_code": None,
        "ressource_title": ro.name,
        "ressource_url": ro.url,
        "ressource_path": None
    },
    "theme_id": theme.id,
    "module_id": module.id,
    "matiere_id": matiere.id,
    "parcour_id": course.parcours_id,
    "parcours_name": course.name
}
```

## Implementation Files

### Backend Models (Source of Truth):
- `skillforge-backend/src/data_ingestion/models/course_content_model.py`
- `skillforge-backend/src/data_ingestion/models/matiere_content_model.py`
- `skillforge-backend/src/data_ingestion/models/module_content_model.py`
- `skillforge-backend/src/data_ingestion/models/theme_content_model.py`
- `skillforge-backend/src/data_ingestion/models/ressource_content_model.py`
- `skillforge-backend/src/data_ingestion/models/ressource_object_content_model.py`

### Frontend Models (Copied from Backend):
- `src/models/course_content.py` ✅
- `src/models/matiere.py` ✅
- `src/models/module.py` ✅
- `src/models/theme.py` ✅
- `src/models/ressource.py` ✅
- `src/models/ressource_object.py` ✅

### Frontend Implementation:
- `chatbot.py` - Main UI with hierarchical navigation ✅
- `src/utils/course_loader.py` - JSON loading and hierarchy traversal ✅
- `src/api/skillforge_client.py` - API context building ✅

## API Integration

### Thread Context (CourseContextStudiRequest):
```python
# From: skillforge-backend/src/facade/request_models/context_request.py
class CourseContextStudiRequest(CourseContextRequest):
    ressource: RessourceDescriptionRequest | None = None
    theme_id: str | None = None
    module_id: str | None = None
    matiere_id: str | None = None
    parcour_id: str | None = None
    parcours_name: str | None = None
```

### Endpoints:
1. `POST /thread/get-all/ids` - Get/create thread for context
2. `GET /thread/{id}/messages` - Retrieve conversation
3. `POST /thread/{id}/query` - Send query with streaming response

## Example JSON Structure (*.json)

```json
{
    "parcours_id": "123",
    "parcours_code": "BAC-DEV",
    "name": "Bachelor Développeur Python",
    "is_demo": false,
    "matieres": [
        {
            "matiere_id": "m1",
            "name": "Programmation",
            "code": "PROG",
            "modules": ["mod1", "mod2"]
        }
    ],
    "modules": [
        {
            "module_id": "mod1",
            "name": "Python Basics",
            "code": "PY-101",
            "matiere_id": "m1",
            "themes": ["t1", "t2"]
        }
    ],
    "themes": [
        {
            "theme_id": "t1",
            "name": "Variables et Types",
            "code": "VAR",
            "module_id": "mod1",
            "ressources": ["r1"]
        }
    ],
    "ressources": [
        {
            "ressource_id": "r1",
            "name": "Introduction",
            "code": "INTRO",
            "theme_id": "t1",
            "ressource_objects": ["ro1"]
        }
    ],
    "ressource_objects": [
        {
            "ressource_object_id": "ro1",
            "name": "Cours Variables",
            "type": "opale",
            "url": "https://ressources.studi.fr/...",
            "hierarchy": {
                "ressource_id": "r1",
                "theme_id": "t1",
                "module_id": "mod1",
                "matiere_id": "m1"
            }
        }
    ]
}
```

## Verification Checklist ✅

- ✅ All model classes copied from backend
- ✅ Hierarchy structure matches exactly
- ✅ Parent-child relationships preserved
- ✅ CourseContent.from_dict() rebuilds relationships
- ✅ Frontend navigation follows hierarchy
- ✅ API context includes all hierarchy levels
- ✅ Thread management uses full context
- ✅ RessourceObject.hierarchy stores full path

## Notes

- **Two-way relationships**: Each level stores both parent reference and children list
- **Flat storage**: CourseContent stores all entities in flat lists, then rebuilds relationships
- **Type safety**: RessourceObject.type can be "pdf", "opale", "video", etc.
- **Context completeness**: API always receives full hierarchy context for optimal AI responses
