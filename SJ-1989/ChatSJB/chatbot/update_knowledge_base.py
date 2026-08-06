import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import spmatrix
from google.genai import Client
from chatbot.parse_notion_text import parse_notion_text


def get_notion_blocks(
        NOTION_API_KEY: str, 
        NOTION_PAGE_ID: str
    ) -> list[str]:
    """
    Sends a request to Notion to retrieve 'blocks' data from a page.
    Parses the data into chunks containing topic and text, finally 
    returning them combined as 'documents'. 
    """
    headers = {
            'Authorization': f'Bearer {NOTION_API_KEY}',
            'Notion-Version': '2022-06-28'
        }

    url = f'https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children'

    all_blocks = []
    next_cursor = None

    while True:

        params = {}

        if next_cursor:
            params['start_cursor'] = next_cursor

        response = requests.get(
                url,
                headers=headers,
                params=params
            )
        
        response.raise_for_status()

        data = response.json()

        all_blocks.extend(
            data['results']
        )

        if not data['has_more']:
            break

        next_cursor = data['next_cursor']

    chunks = parse_notion_text(all_blocks)

    documents = [
        f'Topic: {chunk["topic"]}\n\nText: {chunk["text"]}\n\n'
        for chunk in chunks
    ]

    return documents


def build_tfidf_matrix(documents: list[str]) -> tuple[TfidfVectorizer, spmatrix]:
    """
    Fits a TF-IDF vectorizer on all documents and returns the fitted
    vectorizer along with the TF-IDF document-term matrix.    
    """
    tfidf_vectorizer = TfidfVectorizer()
    tfidf_matrix = tfidf_vectorizer.fit_transform(documents)

    return tfidf_vectorizer, tfidf_matrix


def build_dense_embedding_matrix(llm_client, documents: list[str]):
    """
    Creates dense embeddings for all documents.
    """

    result = llm_client.models.embed_content(
        model="gemini-embedding-001",
        contents=documents
    )

    embeddings = [
        item.values for item in result.embeddings
    ]

    return embeddings


def update_knowledge_base(
    NOTION_API_KEY: str,
    NOTION_PAGE_ID: str,
    llm_client: Client=None
) -> tuple[list[str], TfidfVectorizer, spmatrix]:
    """
    Retrieves documents from Notion and creates a fitted TF-IDF vectorizer
    and matrix for document retrieval.
    """
    documents = get_notion_blocks(NOTION_API_KEY, NOTION_PAGE_ID)
    tfidf_vectorizer, tfidf_matrix = build_tfidf_matrix(documents)

    if llm_client:
        dense_embeddings_matrix = build_dense_embedding_matrix(llm_client, documents)
        return (
            documents, 
            tfidf_vectorizer, 
            tfidf_matrix, 
            dense_embeddings_matrix
        )
    else:
        return (
            documents, 
            tfidf_vectorizer, 
            tfidf_matrix,
         )