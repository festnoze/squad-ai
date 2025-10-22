# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpaleCoursesWebscraper is an educational content extraction and intelligent tutoring system for Studi.fr courses. It scrapes Opale-based (interactive HTML5 learning modules) course content and provides an AI-powered chatbot interface for student Q&A using RAG (Retrieval-Augmented Generation).

## Development Setup

**Virtual Environment:** This project uses a Python virtual environment located at `senv/`.

Always activate the virtual environment before running any commands:
```bash
.\senv\Scripts\activate
```

**Installing Dependencies:**
```bash
python -m pip install -r requirements.txt --upgrade
# OR use the provided batch script:
libs_install.bat
```

**CommonTools Dependency:** This project depends on an internal package `CommonTools` located at `C:/Dev/IA/CommonTools` (installed in editable mode with `-e` flag). This package provides shared utilities for file operations, LLM interactions, and environment management.

## Running the Application

**Start the Streamlit Chatbot:**
```bash
python startup.py
```
This launches the Streamlit web UI at the default port (8501).

## Architecture

### Three Core Services

1. **CourseContentScrapingService** ([course_content_scraping_service.py](course_content_scraping_service.py))
   - Orchestrates web scraping from Studi.fr
   - Uses Selenium for JavaScript-rendered Opale courses
   - Extracts PDFs and converts to Markdown/HTML
   - Saves scraped content to `outputs/{course_name}/`

2. **CourseContentParser** ([course_content_parser.py](course_content_parser.py))
   - Parses course composition JSON files from `inputs/`
   - Builds hierarchical Python object structure
   - Saves analyzed structures to `outputs/analysed_*.json`

3. **CourseContentQueryingService** ([course_content_querying_service.py](course_content_querying_service.py))
   - Implements RAG-based Q&A with LangChain
   - Loads course content and streams LLM responses
   - Uses pedagogical system prompt from `prompts/query_course_content_prompt.txt`

### Hierarchical Data Model

French educational structure represented in [models/](models/):
```
CourseContent (Parcours)
├── Matiere (Subject)
│   └── Module
│       └── Theme
│           └── Ressource (Resource)
│               └── RessourceObject (Learning Object)
```

All models support serialization via `to_dict()` and `from_dict()` methods for JSON persistence. Parent-child relationships are bidirectional with ID-based tracking via `RessourceObjectHierarchy`.

### Web Scraping Workflow

For Opale courses on Studi.fr:
1. Navigate to base course URL
2. Use Selenium to load JavaScript-rendered content
3. Extract "Commencer le cours" link
4. Navigate to content page
5. Find PDF via "Imprimer" button
6. Extract PDF text using pdfminer.six
7. Convert to HTML and Markdown using markdownify
8. Save to `outputs/{course_name}/*.md` and `*.html`

## LLM Configuration

**Configuration File:** `.llm.env.yaml`

Current active model: DeepSeek R1 via OpenRouter
```yaml
- {type: InferenceProvider OpenRouter, model: deepseek/deepseek-r1, timeout: 90, is_reasoning_model: True}
```

Temperature is set to 0.0 for deterministic responses. Multiple provider options are available (OpenAI, Anthropic, Ollama) but commented out.

**Pedagogical Prompt:** System prompt in `prompts/query_course_content_prompt.txt` instructs the LLM to:
- Act as an experienced tutor
- Use only provided course content
- Cite sections by name (not page numbers)
- Keep answers concise (max 10 lines, preferably 1 sentence)
- Use pedagogical techniques (examples, metaphors)

## Code Conventions

- **Async methods:** Prefix with "a" (e.g., `async def aload_course(...)`, `async def aanswer_user_query(...)`)
- **Static methods:** Service classes use `@staticmethod` for utility functions
- **Type hints:** Python 3.10+ style (e.g., `list[str]`, `dict[str, Any]`)
- **French terminology:** Preserved for domain accuracy (Matière, Parcours, Ressource, Thème)
- **Naming:** Methods use action verb prefixes (scrape_, parse_, answer_, load_)

## Streamlit Session Management

- Uses `st.session_state` for conversation history
- Message format: `{'role': 'user'/'assistant', 'content': str}`
- Session initialized in `ChatbotFront.init_session()`

## Data Locations

- **Input:** `inputs/` - Course composition JSONs
  - **Source:** Create the JSON file from the API response of `https://uat-lms-studi.studi.fr/ws/api/v3/courses/parcours`. This endpoint returns all parcours (courses) the user is enrolled in.
  - **Structure:** The JSON contains course enrollment data with the following structure:
    ```json
    {
      "parcours": [{
        "parcoursId": 2760,
        "parcoursCode": "BDP2329",
        "name": "Bachelor Développeur Python 2023-2029",
        "matieres": [
          {
            "matiereId": 49536,
            "modules": [
              {
                "moduleId": 70317,
                "themes": [
                  {
                    "themeId": 128356,
                    "ressources": [
                      {
                        "ressourceId": 123456,
                        "ressourceObjects": [
                          {
                            "ressourceObjectId": 789012,
                            "type": "opale",
                            "url": "https://ressources.studi.fr/..."
                          }
                        ]
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }]
    }
    ```
- **Output:** `outputs/` - Generated content and analyzed structures
  - `outputs/analysed_*.json` - Parsed course hierarchies
  - `outputs/{Course Name}/` - Per-course Markdown and HTML files
- **Prompts:** `prompts/` - System prompts for LLM

## Entry Point

`startup.py` → `ChatbotFront.run()` initializes the Streamlit application.

The chatbot UI ([chatbot.py](chatbot.py)) provides four main workflows via sidebar:
1. Analyze parcours composition from JSON
2. Bulk scrape all courses in a parcours
3. Scrape single course from URL
4. Interactive Q&A on selected course content
