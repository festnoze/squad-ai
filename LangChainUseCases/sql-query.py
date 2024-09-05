from langchain_experimental.sql import SQLDatabaseChain
from langchain_community.llms import SQLDatabase

class QuerySQL:
    def __init__(self, query):
        self.query = query

    def execute(self):
        print(f"Executing query: {self.query}")