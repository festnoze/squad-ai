# RAG Ingestion Pipeline - Generic Process Steps

This document describes the step-by-step process to build a RAG ingestion pipeline, regardless of the document source (files, API calls, web scraping, databases, etc.).

---

## Pipeline Overview

```
[Data Source] → [1. Data Retrieval] → [2. Document Creation] → [3. Optional: LLM Enrichment] → [4. Chunking] → [5. Embedding & Vector Store Insertion] → [6. Service Re-initialization]
```

---

## Step 1: Data Retrieval (Project-Specific)

**Goal:** Collect raw data from your source(s).

**This step is always project-specific.** The data source determines the retrieval logic:

| Source Type       | Example Implementation                                      |
| ----------------- | ----------------------------------------------------------- |
| Files (JSON, CSV) | Load and parse files from a directory                       |
| REST API          | Call endpoints, paginate, collect responses                  |
| Web scraping      | Crawl pages, extract structured content                     |
| Database          | Query tables, export rows                                   |
| Mixed             | Combine multiple sources (e.g., API + scraping as in Studi) |

**Output:** Raw data (dicts, JSON objects, text blobs) ready for document creation.

**What belongs in your project:** All retrieval logic, API clients, scrapers, file loaders.
**What belongs in common-tools:** Nothing — this is inherently domain-specific.

---

## Step 2: Document Creation with Metadata (Project-Specific)

**Goal:** Transform raw data into LangChain `Document` objects with meaningful metadata.

### 2.1 - Build Document Content

For each data item, create the `page_content` string. This could be:
- The full text of an article
- A concatenation of structured fields (title + description + details)
- A formatted representation of API response data

### 2.2 - Attach Metadata

Metadata enables filtering at query time. Define your metadata schema based on your domain:

```python
from langchain.docstore.document import Document

doc = Document(
    page_content="Full text content here...",
    metadata={
        "doc_id": "unique-identifier",       # Required: unique ID for tracing
        "type": "article",                    # Required: document category
        "name": "Document Title",             # Required: human-readable name
        "source": "api/web/file",             # Recommended: data origin
        # ... any domain-specific fields for filtering
    }
)
```

### 2.3 - Organize Documents

Separate documents into logical groups if needed (e.g., main docs vs. docs requiring enrichment). Return them as `list[Document]`.

**What belongs in your project:** Metadata schema definition, field mappings, content formatting, entity-specific processing, relationship mapping between entities.
**What belongs in common-tools:** The `Document` class itself (from LangChain).

---

## Step 3 (Optional): LLM-Based Document Enrichment (Generic)

**Goal:** Use an LLM to generate summaries, Q&A pairs, or enriched representations of documents before indexing.

This step is **optional** but can significantly improve retrieval quality by creating semantically richer document representations.

### 3.1 - Summarization

For each document, generate a concise summary that preserves key information:

```python
from common_tools.RAG.rag_ingestion_pipeline.summary_and_questions.summary_and_questions_chunks_service import SummaryAndQuestionsChunksService

objects = await SummaryAndQuestionsChunksService.build_summaries_and_chunks_by_questions_objects_from_docs_async(
    documents=your_documents,
    llm_and_fallback=[primary_llm, fallback_llm_1, fallback_llm_2],
    load_existing_summaries_and_questions_from_file=True,  # Cache expensive LLM calls
    file_path="./outputs",
    existing_summaries_and_questions_filename="my_summaries_cache"
)
```

### 3.2 - Chunk Extraction from Summaries

The LLM splits each summary into semantic chunks (2-40 chunks, max 500 words each), grouping related information together.

### 3.3 - Question Generation per Chunk

For each chunk, the LLM generates questions that the chunk answers. Questions must be:
- **Atomic:** One subject per question
- **Complete:** Standalone, understandable without external context
- **Exhaustive:** Cover all information in the chunk

### 3.4 - Convert to Indexable Documents

Convert the enriched objects back to `Document` list for indexing:

```python
enriched_docs = SummaryAndQuestionsChunksService \
    .build_chunks_splitted_by_questions_from_summaries_and_chunks_by_questions_objects(objects)
```

Configuration via environment variables:
- `IS_SUMMARIZED_DATA` — Enable/disable summarization
- `IS_QUESTIONS_CREATED_FROM_DATA` — Generate Q&A documents
- `IS_MIXED_QUESTIONS_AND_DATA` — Merge questions with chunk content or keep separate

**What belongs in your project:** Decision to enable/disable, prompt customization, cache file paths.
**What belongs in common-tools (already there):** `SummaryAndQuestionsChunksService`, `SummaryAndQuestionsChunksCreation`, `DocWithSummaryChunksAndQuestions` model, prompt templates, batch processing with caching.

---

## Step 4: Document Chunking (Generic)

**Goal:** Split documents into smaller chunks suitable for embedding and retrieval.

```python
from common_tools.RAG.rag_ingestion_pipeline.rag_ingestion_pipeline import RagIngestionPipeline

pipeline = RagIngestionPipeline(rag_service)
chunks = pipeline.chunk_documents(documents=all_documents)
```

### How it works

1. Each document is split using `RecursiveCharacterTextSplitter` with hierarchical separators: `"\n\n"` → `"\r\n"` → `"\n"` → `" "` → `""`
2. Default parameters:
   - `chunk_size`: 2000 characters
   - `chunk_overlap`: 100 characters
   - `max_chunk_size`: 5461 words (validation)
3. Each chunk receives a unique UUID in its metadata
4. Original document metadata is preserved on each chunk

**What belongs in your project:** Possibly custom chunk size parameters if your data requires it.
**What belongs in common-tools (already there):** `RagChunking`, `RagIngestionPipeline.chunk_documents()`.

---

## Step 5: Embedding & Vector Store Insertion (Generic)

**Goal:** Embed document chunks as vectors and store them in a vector database.

```python
rag_service.vectorstore = pipeline.embed_chunks_then_add_to_vectorstore(
    docs_chunks=chunks,
    vector_db_type=rag_service.vector_db_type,
    collection_name=rag_service.vector_db_name,
    delete_existing=True,
    load_embeddings_from_file_if_exists=True,  # Cache embeddings to avoid recomputation
)
```

### 5.1 - Embedding Model Selection

Configured via environment variables (`EMBEDDING_MODEL`, `EMBEDDING_SIZE`). Supported providers:
- **OpenAI:** text-embedding-3-small, text-embedding-3-large, ada-002
- **Ollama:** all-minilm, mistral, llama3 (local)
- **SentenceTransformers:** all-MiniLM-L6-v2, all-mpnet-base-v2 (local)

### 5.2 - Vector Database Selection

Configured via `VECTOR_DB_TYPE`. Supported databases:

| Database   | Type  | Hybrid Search | Notes                             |
| ---------- | ----- | ------------- | --------------------------------- |
| ChromaDB   | Local | No            | Simple setup, local persistence   |
| Qdrant     | Both  | No            | Local or cloud                    |
| Pinecone   | Cloud | Yes (native)  | Dense + sparse vectors in one index |

### 5.3 - Hybrid Search (Optional)

When using Pinecone with `IS_COMMON_DB_FOR_SPARSE_AND_DENSE_VECTORS=True`:
- **Dense vectors:** Semantic similarity (from embedding model)
- **Sparse vectors:** BM25 keyword matching (computed by `SparseVectorEmbedding`)
- Both stored in the same index for combined retrieval

### 5.4 - Embedding Caching

When `load_embeddings_from_file_if_exists=True`, embeddings are saved/loaded from:
- Dense vectors: `.npy` files
- Sparse vectors: `.json` files
- Vectorizer state: `.pkl` files

This avoids recomputing expensive embeddings on subsequent runs.

### 5.5 - Batch Processing

Large document sets are processed in batches (configurable batch size) to manage memory and API rate limits.

**What belongs in your project:** Environment configuration (which DB, which embedding model, collection name).
**What belongs in common-tools (already there):** `RagIngestionPipeline`, `SparseVectorEmbedding`, `RagService`, `EmbeddingModelFactory`, all vector DB adapters.

---

## Step 6: Service Re-initialization (Project-Specific)

**Goal:** Reload the RAG service with the newly populated vector store so the inference pipeline can use it.

```python
# Reload the service to pick up the new vectorstore
rag_service = RagServiceFactory.build_from_env_config()
```

This ensures:
- The vectorstore reference is updated
- BM25 document index (if used) is reloaded from the JSON file
- The inference pipeline is ready for queries

**What belongs in your project:** Application-level re-initialization logic.
**What belongs in common-tools (already there):** `RagServiceFactory.build_from_env_config()`.

---

## Complete Minimal Example

```python
from langchain.docstore.document import Document
from common_tools.RAG.rag_service import RagServiceFactory
from common_tools.RAG.rag_ingestion_pipeline.rag_ingestion_pipeline import RagIngestionPipeline

# --- Step 1: Retrieve data (YOUR CODE) ---
raw_data = your_data_retrieval_function()

# --- Step 2: Create documents with metadata (YOUR CODE) ---
documents = []
for item in raw_data:
    doc = Document(
        page_content=item["content"],
        metadata={
            "doc_id": item["id"],
            "type": item["category"],
            "name": item["title"],
            "source": "your_source",
        }
    )
    documents.append(doc)

# --- Step 3 (Optional): LLM enrichment (GENERIC - from common-tools) ---
# Uncomment if you want summarization + Q&A generation:
#
# from common_tools.RAG.rag_ingestion_pipeline.summary_and_questions.summary_and_questions_chunks_service import SummaryAndQuestionsChunksService
# enriched_objects = await SummaryAndQuestionsChunksService \
#     .build_summaries_and_chunks_by_questions_objects_from_docs_async(
#         documents=documents,
#         llm_and_fallback=[rag_service.llm_1, rag_service.llm_2],
#         load_existing_summaries_and_questions_from_file=True,
#     )
# documents = SummaryAndQuestionsChunksService \
#     .build_chunks_splitted_by_questions_from_summaries_and_chunks_by_questions_objects(enriched_objects)

# --- Step 4: Chunk documents (GENERIC - from common-tools) ---
rag_service = RagServiceFactory.build_from_env_config()
pipeline = RagIngestionPipeline(rag_service)
chunks = pipeline.chunk_documents(documents=documents)

# --- Step 5: Embed & store in vector DB (GENERIC - from common-tools) ---
rag_service.vectorstore = pipeline.embed_chunks_then_add_to_vectorstore(
    docs_chunks=chunks,
    vector_db_type=rag_service.vector_db_type,
    collection_name=rag_service.vector_db_name,
    delete_existing=True,
    load_embeddings_from_file_if_exists=True,
)

# --- Step 6: Re-init service (YOUR CODE) ---
# Reload to pick up new vectorstore for inference
rag_service = RagServiceFactory.build_from_env_config()
```

---

## Summary: Generic vs Project-Specific

| Step | What | Where |
| ---- | ---- | ----- |
| 1. Data Retrieval | API clients, file loaders, scrapers | **Your project** |
| 2. Document Creation | Metadata schema, content formatting | **Your project** |
| 3. LLM Enrichment | Summarization, Q&A generation, caching | **common-tools** (`SummaryAndQuestionsChunksService`) |
| 4. Chunking | Text splitting with overlap | **common-tools** (`RagChunking`, `RagIngestionPipeline`) |
| 5. Embedding & Storage | Vector embedding, DB insertion, caching | **common-tools** (`RagIngestionPipeline`, `SparseVectorEmbedding`) |
| 6. Service Re-init | Reload vectorstore for inference | **common-tools** (`RagServiceFactory`) + **your project** (app-level wiring) |

---

## Environment Configuration Reference

```env
# Embedding
EMBEDDING_MODEL=OpenAI_TextEmbedding3Small
EMBEDDING_SIZE=500

# Vector database
VECTOR_DB_TYPE=pinecone          # chroma | qdrant | pinecone
VECTOR_DB_NAME=my-project

# LLM enrichment options
IS_SUMMARIZED_DATA=True
IS_QUESTIONS_CREATED_FROM_DATA=True
IS_MIXED_QUESTIONS_AND_DATA=False

# Hybrid search (Pinecone only)
IS_COMMON_DB_FOR_SPARSE_AND_DENSE_VECTORS=True
BM25_STORAGE_AS_DB_SPARSE_VECTORS=True
```
