from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse import csr_matrix

# common tools imports
from common_tools.helpers.txt_helper import txt

class SparseVectorEmbedding:
    def embed_documents_as_sparse_vectors(docs: list[str]) -> csr_matrix:
        # Vectorizing documents into sparse vectors with TfidfVectorizer
        vectorizer = TfidfVectorizer()
        sparse_vectors = vectorizer.fit_transform(docs)  # Sparse matrix
        txt.print(f"Shape of the sparse vectors: {sparse_vectors.shape}")
        vocabulary_size = len(vectorizer.get_feature_names_out())  # Total unique tokens
        txt.print(f"Size of the sparse vectors: {vocabulary_size}")

        # Conversion of TF-IDF vectors to BM25-compatible format (normalizes and adjusts weights)
        bm25_vectors = csr_matrix(sparse_vectors)  # Sparse matrix
        return bm25_vectors