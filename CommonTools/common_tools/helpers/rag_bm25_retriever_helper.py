from rank_bm25 import BM25Okapi
import numpy as np

class BM25RetrieverHelper:
    @staticmethod
    def find_best_match_bm25(reference_values:list[str], value_to_compare:str):        
        tokenized_corpus = [value.lower().split() for value in reference_values]
        
        # Initialize BM25
        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = value_to_compare.lower().split()
        
        # Get BM25 scores
        scores = bm25.get_scores(tokenized_query)

        # Normalize scores (min-max normalizer [0, 1])
        min_score = scores.min()
        max_score = scores.max()        
        if max_score > min_score:
            normalized_scores = (scores - min_score) / (max_score - min_score)
        else:
            normalized_scores = np.zeros_like(scores) 
        
        best_match_index = np.argmax(normalized_scores)
        best_score = normalized_scores[best_match_index]
        
        best_match = reference_values[best_match_index]        
        return best_match, best_score
    
    @staticmethod
    async def find_best_match_bm25_async(reference_values: list[str], value_to_compare: str):
        tokenized_corpus = [value.lower().split() for value in reference_values]
        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = value_to_compare.lower().split()

        # Get BM25 scores
        scores = bm25.get_scores(tokenized_query)

        # Normalize scores (min-max normalizer [0, 1])
        min_score = scores.min()
        max_score = scores.max()
        if max_score > min_score:
            normalized_scores = (scores - min_score) / (max_score - min_score)
        else:
            normalized_scores = np.zeros_like(scores)

        best_match_index = np.argmax(normalized_scores)
        best_score = normalized_scores[best_match_index]

        best_match = reference_values[best_match_index]
        return best_match, best_score