import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse import csr_matrix

# common tools imports
from common_tools.helpers.txt_helper import txt

class SparseVectorEmbedding:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.vectorizer = TfidfVectorizer(norm=None, smooth_idf=False, use_idf=True)
        self.avg_doc_length = None  # Stores the average document length after initial embedding

    def embed_documents_as_sparse_vectors_for_TF_IDF(self, docs: list[str]) -> csr_matrix:
        # Vectorizing documents into sparse vectors with TfidfVectorizer
        sparse_vectors = self.vectorizer.fit_transform(docs)  # Sparse matrix
        txt.print(f"Shape of the sparse vectors: {sparse_vectors.shape}")
        vocabulary_size = len(self.vectorizer.get_feature_names_out())  # Total unique tokens
        txt.print(f"Size of the sparse vectors: {vocabulary_size}")

        # Conversion of TF-IDF vectors to BM25-compatible format (normalizes and adjusts weights)
        bm25_vectors = csr_matrix(sparse_vectors)  # Sparse matrix
        return bm25_vectors

    def embed_documents_as_sparse_vectors_for_BM25_initial(self, documents):
        """
        Embeds a set of documents as BM25-compatible sparse vectors. 
        Learns vocabulary, IDF, and document statistics during this process.
        """
        # Learn vocabulary and IDF, calculate sparse TF matrix
        tf = self.vectorizer.fit_transform(documents)  # Sparse term-frequency matrix

        # Compute average document length
        doc_lengths = np.array(tf.sum(axis=1)).flatten()  # Row-wise sum (document lengths)
        self.avg_doc_length = np.mean(doc_lengths)

        # Compute IDF values
        idf = self.vectorizer.idf_

        # Apply BM25 weighting
        rows, cols = tf.nonzero()
        bm25_data = []
        for row, col in zip(rows, cols):
            tf_value = tf[row, col]
            doc_length = doc_lengths[row]
            idf_value = idf[col]
            denominator = tf_value + self.k1 * (1 - self.b + self.b * (doc_length / self.avg_doc_length))
            bm25_value = idf_value * ((tf_value * (self.k1 + 1)) / denominator)
            bm25_data.append(bm25_value)

        # Construct sparse BM25 matrix
        bm25 = csr_matrix((bm25_data, (rows, cols)), shape=tf.shape)
        return bm25

    def embed_documents_as_sparse_vectors_for_BM25_upon_previous_vocabulary(self, new_documents):
        """
        Embeds a new set of documents as BM25-compatible sparse vectors 
        using the vocabulary and statistics learned from the initial set of documents.
        """
        if self.avg_doc_length is None:
            raise ValueError("The vectorizer needs to embed the initial documents first (call embed_documents_as_sparse_vectors_for_BM25_initial).")
        
        # Transform using the existing vocabulary
        tf = self.vectorizer.transform(new_documents)  # Sparse term-frequency matrix
        doc_lengths = np.array(tf.sum(axis=1)).flatten()  # Row-wise sum (document lengths)

        # Apply BM25 weighting
        rows, cols = tf.nonzero()
        bm25_data = []
        for row, col in zip(rows, cols):
            tf_value = tf[row, col]
            doc_length = doc_lengths[row]
            idf_value = self.vectorizer.idf_[col]
            denominator = tf_value + self.k1 * (1 - self.b + self.b * (doc_length / self.avg_doc_length))
            bm25_value = idf_value * ((tf_value * (self.k1 + 1)) / denominator)
            bm25_data.append(bm25_value)

        # Construct sparse BM25 matrix
        bm25 = csr_matrix((bm25_data, (rows, cols)), shape=tf.shape)
        return bm25