# Search Patterns Reference

## Finding Service Files

```bash
# All service files
Glob: src/application/*_service.py

# Specific entity service
Grep: class {Entity}Service
Path: src/application/
```

## Method Search Patterns

### By Action Type

**CREATE**
```
Pattern: async def acreate_{entity}
Examples:
  - acreate_new_thread
  - acreate_or_update_user
```

**RETRIEVE/GET**
```
Pattern: async def aget_{entity} OR async def aretrieve_{entity}
Examples:
  - aget_user_by_lms_user_id
  - aget_retrieve_or_create_user
  - aget_content_by_filter
  - aretrieve_user_infos_from_lms_api
```

**UPDATE**
```
Pattern: async def aupdate_{entity}
Examples:
  - aupdate_context_metadata
  - aupdate_user_preference
```

**DELETE**
```
Pattern: async def adelete_{entity}
Examples:
  - adelete_course_by_id
  - aclear_thread_messages
```

**STREAMING**
```
Pattern: async def astream_
Examples:
  - astream_llm_response_and_persist
  - astream_query_response
```

**SCRAPING/EXTERNAL**
```
Pattern: async def ascrape_ OR async def afetch_
Examples:
  - ascrape_parcours_all_contents
  - ascrape_course_content_from_url
```

**BULK/BATCH**
```
Pattern: async def aexport_ OR async def aimport_ OR async def abulk_
Examples:
  - aexport_contents_to_json_files
  - aimport_contents_from_json_files
  - asummarize_all_contents
```

### By Entity/Domain

**User operations**
```
File: user_service.py
Patterns:
  - async def.*user
  - async def.*school
```

**Thread/Conversation operations**
```
File: thread_service.py
Patterns:
  - async def.*thread
  - async def.*message
  - async def.*query
  - async def.*stream
```

**Content operations**
```
File: content_service.py
Patterns:
  - async def.*content
  - async def.*scrape
```

**Course operations**
```
File: course_hierarchy_service.py
Patterns:
  - async def.*course
  - async def.*hierarchy
  - async def.*parcours
```

**Summary operations**
```
File: summary_service.py
Patterns:
  - async def.*summar
```

## Advanced Search

### Find methods with specific parameter
```
Pattern: async def a.*\(self,.*{param_name}:
```

### Find methods returning generators (streaming)
```
Pattern: -> AsyncGenerator
```

### Find methods with specific dependency calls
```
# Methods calling a specific repository
Pattern: self\.{entity}_repository\.a

# Methods calling another service
Pattern: self\.{entity}_service\.a
```

### Find private helper methods
```
Pattern: async def _a
Pattern: def _[a-z]
```

## Service-to-Repository Mapping

| Service | Primary Repository | Other Dependencies |
|---------|-------------------|-------------------|
| UserService | UserRepository | SchoolRepository |
| ThreadService | ThreadRepository | ContextRepository, (UserService, ContentService, LlmService) |
| ContentService | ContentRepository | (CourseHierarchyService) |
| CourseHierarchyService | CourseHierarchyRepository | - |
| SummaryService | ContentRepository | (LlmService) |

## Dependency Injection Config

```
File: src/API/dependency_injection_config.py
Patterns:
  - container\[{Entity}Service\]
  - container\[{Entity}Repository\]
```
