# Search Patterns Reference

## Finding Repository Files

```bash
# All repository files
Glob: src/infrastructure/*_repository.py

# Specific entity repository
Grep: class {Entity}Repository
```

## Method Search Patterns

### By Operation Type

**GET (single)**
```
Pattern: async def aget_{entity}_by_
Examples:
  - aget_user_by_id
  - aget_user_by_lms_user_id
  - aget_thread_by_id
  - aget_school_by_name
```

**GET (multiple)**
```
Pattern: async def aget_{entities} OR async def aget_all_{entities}
Examples:
  - aget_threads_ids_by_user_and_context
  - aget_all_quick_actions
  - aget_contents_batch
```

**CREATE**
```
Pattern: async def acreate_{entity}
Examples:
  - acreate_user
  - acreate_thread
  - acreate_school
```

**UPDATE**
```
Pattern: async def aupdate_{entity}
Examples:
  - aupdate_user
  - aupdate_school
```

**DELETE**
```
Pattern: async def adelete_{entity} OR async def aclear_{entities}
Examples:
  - adelete_content_by_id
  - aclear_thread_messages
  - adelete_all_thread_messages
```

**UPSERT**
```
Pattern: async def acreate_or_update_{entity} OR async def acreate_or_get_{entity}
Examples:
  - acreate_or_update
  - acreate_or_update_user_preference
  - acreate_or_get_by_name
```

**CHECK/EXISTS**
```
Pattern: async def adoes_{entity}_exist OR async def a*_exists
Examples:
  - adoes_user_exists_by_id
  - adoes_thread_exist
  - astatic_data_exists
```

**COUNT**
```
Pattern: async def aget_{entity}_count OR func.count
Examples:
  - aget_thread_messages_count
  - aget_user_message_count_since_start_of_day
```

### By Entity

**User operations**
```
Grep in: user_repository.py
Patterns:
  - async def.*user
  - async def.*preference
```

**Thread/Message operations**
```
Grep in: thread_repository.py
Patterns:
  - async def.*thread
  - async def.*message
```

**Role operations**
```
Grep in: role_repository.py
Patterns:
  - async def.*role
```

**School operations**
```
Grep in: school_repository.py
Patterns:
  - async def.*school
```

**Content operations**
```
Grep in: content_repository.py
Patterns:
  - async def.*content
```

## Advanced Search

### Find methods with specific parameter
```
Pattern: async def a.*\(self, session: AsyncSession, {param_name}:
```

### Find cached methods
```
Pattern: @cache_retrieval_or_caching
```

### Find methods with special decorators
```
Pattern: @no_auto_session
Pattern: @non_cancellable
```

### Find private helper methods
```
Pattern: async def _a.*_query\(
Pattern: async def _a.*_in_session\(
```

## Entity-to-Table Mapping

| Entity Class | Table Name | Repository |
|--------------|------------|------------|
| UserEntity | users | UserRepository |
| UserPreferenceEntity | user_preferences | UserRepository |
| ThreadEntity | threads | ThreadRepository |
| MessageEntity | messages | ThreadRepository |
| RoleEntity | roles | RoleRepository |
| SchoolEntity | schools | SchoolRepository |
| ContentEntity | contents | ContentRepository |
| QuickActionEntity | quick_actions | QuickActionRepository |
| MigrationHistoryEntity | _migration_history | MigrationHistoryRepository |
