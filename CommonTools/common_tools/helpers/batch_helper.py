import json
import sys
from typing import Generator, Union

class BatchHelper:
    @staticmethod
    def batch_split_by_count(items_to_batch: list, batch_size: int) -> list[list]:
        """
        Splits a list of items into batches of a specified size.
        Returns a list of batches.
        """
        return [items_to_batch[i:i + batch_size] for i in range(0, len(items_to_batch), batch_size)]

    @staticmethod
    def batch_split_by_size_in_kilo_bytes(items_to_batch: list, max_kilo_bytes: float) -> list[list]:
        """
        Splits a list of documents into batches where the cumulative size in KB 
        does not exceed the specified max_kilo_bytes.
        Returns a list of batches.
        """
        batches = []
        current_batch = []
        current_size = 0.0

        for item in items_to_batch:
            item_size = BatchHelper.get_size_in_kilo_bytes(item)

            # Check if adding this document exceeds the maximum batch size
            if current_size + item_size > max_kilo_bytes:
                batches.append(current_batch)  # Append the current batch
                current_batch = [item]  # Start a new batch
                current_size = item_size
            else:
                current_batch.append(item)
                current_size += item_size

        # Append any remaining documents in the final batch
        if current_batch:
            batches.append(current_batch)

        return batches
    
    @staticmethod
    def get_size_in_kilo_bytes(instance: Union[dict, list]) -> float:
        """
        Calculates the size of an entry in kilo-bytes.
        Converts the entry to JSON and measures its byte size.
        """
        try:
            serialized = json.dumps(instance).encode('utf-8')
            size_in_kilo_bytes = len(serialized) / 1024
            return size_in_kilo_bytes
        except Exception as e:
            print(f"Failed to calculate size of entry: {e}")
            return sys.maxsize  # Return a very large size in case of failure