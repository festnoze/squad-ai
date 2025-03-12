class Helper:
    @staticmethod
    def flatten_inner_lists(values: list[any]) -> list[str]:
        if not values: 
            return None
        flatten_list: list[str] = []
        for item in values:
            if isinstance(item, list):
                flatten_list.extend(Helper.flatten_inner_lists(item))
            elif isinstance(item, str):
                flatten_list.append(item)
        return flatten_list