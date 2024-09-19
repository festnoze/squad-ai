class RagMetadataHelper:
    
    @staticmethod
    def has_manual_filters(question: str) -> bool:
        return  question.__contains__("filters:") or question.__contains__("filtres :")
    
    @staticmethod
    def extract_manual_filters(question: str) -> tuple[dict, str]:
        filters = {}
        if question.__contains__("filters:"):
            filters_str = question.split("filters:")[1]
            question = question.split("filters:")[0]
        elif question.__contains__("filtres :"):
            filters_str = question.split("filtres :")[1]
            question = question.split("filtres :")[0]
        filters_str = filters_str.strip()
        filters = RagMetadataHelper.get_filters_from_str(filters_str)
        return filters, question
    
    @staticmethod
    def get_filters_from_str(filters_str: str) -> dict:
        filters = []
        filters_list = filters_str.lower().split(',')

        for filter in filters_list:
            # functional_type: Controller, Service, Repository, ...
            if "controller" in filter or "service" in filter or "repository" in filter:
                # Ensure the first letter is uppercase
                functional_type = filter.strip().capitalize()
                filters.append({"functional_type": functional_type})
            # summary_kind: class, method, (property, enum_member), ...
            elif "method" in filter or "méthode" in filter:
                filters.append({"summary_kind": "method"})
            elif "class" in filter:
                filters.append({"summary_kind": "class"})

        # If there are more than one filters, wrap in "$and", otherwise return a single filter
        if len(filters) > 1:
            return {"$and": filters}
        elif len(filters) == 1:
            return filters[0]  # Just return the single condition directly
        else:
            return {}  # Return an empty filter if no conditions found
        
    @staticmethod
    def get_default_filters() -> dict:
        return {
                "$and": [
                    {"functional_type": "Controller"},
                    {"summary_kind": "method"}
                ]
            }

