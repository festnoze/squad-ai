Common tools

Common tools contains a bunch of helpers methods of common usage, which are embeded into this package to keep the code factorized and ease their reusability.
The provided tools range from low-level needs, like string, json or file management.
To high level AI tools (which will be in a separate library in the future), including Langchain powered tools to handle advanced LLM querying (with output parsing, fallbacks, paralellization and batching), and RAG tools, like a complete and modulable inference pipeline including pre-treatment (query translation, multi-querying,metadata extraction & pre-filtering), hybrid search (BM25 & vector search), and post-treatment. 