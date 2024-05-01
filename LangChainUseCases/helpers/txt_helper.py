class txt:
    @staticmethod
    def get_content(response: any) -> str:
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = response
        return content