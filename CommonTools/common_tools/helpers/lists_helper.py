class Lists:
    def chunk_list_to_fixed_size_lists(lst: list, batch_size: int):
        for i in range(0, len(lst), batch_size):
            yield lst[i:i + batch_size]
    
    def chunk_dict_to_fixed_size_lists(dict: dict, batch_size: int):
        lst = list(dict)
        return Lists.chunk_list_to_fixed_size_lists(lst, batch_size)