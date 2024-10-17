<H1>______ Common tools ______</H1>

<H3>Presentation</H3>
**Common tools** contains a bunch of helpers methods of common usage, which are embeded into this package to keep the code factorized and ease their reusability.


<H3>Includes</H3>
The provided tools range from:

- Low-level helpers, like for: string, json or file management.

- To higher level AI tools (which will be in a separate library in the future), including:
  
  - **LLM querying** tools (including: output parsing, fallbacks, paralellization and batching) powered by Langchain,
  
  - **rag** toolbox, including:
    
    - A complete and modulable **injection pipeline** with: metadata handling, chunking, embedding, vector database creation, and querying.
    
    - A complete and modulable **inference pipeline** with: pre-treatment (query translation, multi-querying,metadata extraction & pre-filtering), hybrid search (BM25 & vector search), and post-treatment. 
  
  - **Agents & tools**.


<u>*Tips:*</u>

- Look into `setup.py` file, the required packages are listed in: `install_requires` section.
- To install locally this package from another project, execute from the terminal: `pip install -e C:/Dev/squad-ai/CommonTools`