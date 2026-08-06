import logging
from numpy.typing import NDArray

import numpy as np
from google import genai
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

import config

from chatbot.update_knowledge_base import update_knowledge_base
from chatbot.prompts.v1 import build_QA_prompt


logger = logging.getLogger(__name__)

if config.USE_AI:
    llm_client = genai.Client(
        api_key=config.GEMINI_API_KEY
    )

    (
        documents,
        tfidf_vectorizer,
        tfidf_matrix,
        dense_embeddings_matrix,
    ) = update_knowledge_base(
        config.NOTION_API_KEY,
        config.NOTION_PAGE_ID,
        llm_client
    )

else:
    (
        documents,
        tfidf_vectorizer,
        tfidf_matrix
    ) = update_knowledge_base(
        config.NOTION_API_KEY,
        config.NOTION_PAGE_ID
    )


def get_tfidf_scores(query: str) -> NDArray[np.float64]:
    """
    Transforms the user query into tf-idf vectors.
    """
    query_vector = tfidf_vectorizer.transform([query])
    return cosine_similarity(
        query_vector, 
        tfidf_matrix
    )[0]


def get_dense_embedding_scores(query: str) -> NDArray[np.float64]:
    """
    Transforms the user query into dense embedding vectors. 
    """
    result = llm_client.models.embed_content(
        model='gemini-embedding-001',
        contents=query,
    )
    query_embedding = result.embeddings[0].values

    return cosine_similarity(
        [query_embedding],
        dense_embeddings_matrix,
    )[0]

def get_hybrid_scores(query: str) -> NDArray[np.float64]:
    """
    Combines TF-IDF and dense embedding similarity scores. 
    """
    tfidf = get_tfidf_scores(query)
    dense_embeddings = get_dense_embedding_scores(query)

    scaler = MinMaxScaler()

    tfidf = scaler.fit_transform(
        tfidf.reshape(-1, 1)
    ).flatten()

    dense_embeddings = scaler.fit_transform(
        dense_embeddings .reshape(-1, 1)
    ).flatten()

    return (
        config.TFIDF_WEIGHT * tfidf +
        config.DENSE_EMBEDDINGS_WEIGHT * dense_embeddings
    )

def get_best_k_chunks(
        scores: NDArray[np.float64],
        human_readable: bool = False,
    ) -> str:
    """
    Uses similarity scores to return the k most relevant 
    context chunks for LLM summarisation. 
    """
    best = scores.argsort()[::-1][:config.CHUNKS_USED]

    logger.info(
        'top_hit=%s', 
        documents[best[0]].split('Topic:')[1].split('\n\n')[0].strip()
    )

    if human_readable:
        best_k_chunks = [
                f'\n\n ### {i}.\n\n{documents[num]} \n\n ---'
                for i, num in enumerate(best, start=1)
            ]

        return '<br>' + '\n\n'.join(best_k_chunks) + '\n\n<br>'

    else:
        best_k_chunks = [
            f'\n\n{documents[num]}'
            for num in best
        ]

        return ''.join(best_k_chunks)


def generate_llm_response(query: str, context: str) -> str:
    """
    Build a prompt and generate a response from an LLM model.
    """
    try:
        prompt = build_QA_prompt(query, context)

        response = llm_client.models.generate_content(
            model=config.MODEL, 
            contents=prompt
        )

        return response.text or ''

    except Exception:
        return ''


def chatbot(query: str) -> str:
    """
    Processes a user query by retrieving relevant context using the
    configured retrieval method and, if enabled, generates a response
    using the LLM. Falls back to TF-IDF retrieval if response generation
    fails or AI is disabled.
    """
    if not config.USE_AI:
        if not config.RETRIEVAL_METHOD == 'tfidf':
            logger.warning(
                'message=you must set USE_AI to true to use %s for retrieval',
                config.RETRIEVAL_METHOD
            )
        retrieval_method = 'tfidf'
    else:
        retrieval_method = config.RETRIEVAL_METHOD

    logger.info('query=%s', query)
    logger.info(
        'settings=[ai:%s, retrieval:%s]', 
        config.USE_AI, 
        retrieval_method
    )

    def fallback_response():
        response = get_best_k_chunks(
            get_tfidf_scores(query),
            human_readable=True
        )
        logger.info('response=%s', response.split('Topic:')[1].split('\n\n')[0].strip())
        return response

    if not config.USE_AI:
        return fallback_response()

    if config.RETRIEVAL_METHOD == 'dense_embeddings':
        context = get_best_k_chunks(
            get_dense_embedding_scores(query)
        )
        response = generate_llm_response(query, context)

        if response:
            logger.info('response=%s', response)
            return response
        else:
            return fallback_response()
        
    elif config.RETRIEVAL_METHOD == 'hybrid':
        context = get_best_k_chunks(
            get_hybrid_scores(query)
        )
        response = generate_llm_response(query, context)

        if response:
            logger.info('response=%s', response)
            return response
        else:
            return fallback_response()

    else:
        context = get_best_k_chunks(
            get_tfidf_scores(query)
        )
        response = generate_llm_response(query, context)

        if response:
            return response
        else:
            return fallback_response()