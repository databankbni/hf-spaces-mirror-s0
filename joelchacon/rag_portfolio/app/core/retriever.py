class Retriever:
    def __init__(self, vectorstore):
        self.retriever = vectorstore.as_retriever(search_kwargs={"k": 6})

    def retrieve(self, query: str):
        return self.retriever.invoke(query)
