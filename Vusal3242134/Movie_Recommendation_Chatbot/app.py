import gradio as gr
import numpy as np
import tensorflow as tf
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
from transformers import TFAutoModel, TFAutoModelForSequenceClassification, AutoTokenizer

# ---------------------------------------------------------------------------
# Everything below uses ONLY TensorFlow (no PyTorch, no sentence-transformers
# package). Both checkpoints ship native tf_model.h5 weights, so nothing
# needs to be converted -- this avoids the TF/PyTorch backend-mixing segfault
# entirely.
# ---------------------------------------------------------------------------

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CLASSIFIER_MODEL_NAME = "Vusal3242134/Classify_Emotions_NEW"

# Embedding model (replaces SentenceTransformer, same underlying checkpoint)
embed_tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL_NAME)
embed_model = TFAutoModel.from_pretrained(EMBED_MODEL_NAME)

# Emotion classifier
tokenizer = AutoTokenizer.from_pretrained(CLASSIFIER_MODEL_NAME)
model = TFAutoModelForSequenceClassification.from_pretrained(CLASSIFIER_MODEL_NAME)

# Load dataset
df = pd.read_csv('tmdb_movies.csv')
df.dropna(subset=['Plot Summary'], inplace=True)

# Genre dictionary
genre_dict = df.groupby('Genres')['Movie Name'].apply(list).to_dict()

# Manual keyword mapping
manual_map = {
    "crime": "Crime",
    "scared": "Horror",
    "love": "Romance",
    "sad": "Drama",
    "depressed": "Drama",
    "funny": "Comedy",
    "laugh": "Comedy",
    "bad": "Drama",
    "mad": "Crime",
    "angry": "Crime",
    "upset": "Drama",
    "lonely": "Drama",
    "happy": "Comedy",
    "joy": "Comedy",
    "terrified": "Horror",
    "nervous": "Horror",
    "excited": "Comedy",
    "cheerful": "Comedy"
}


def mean_pooling(model_output, attention_mask):
    """Mean-pool token embeddings, weighted by the attention mask.
    TF equivalent of the standard sentence-transformers pooling step."""
    token_embeddings = model_output[0]  # (batch, seq_len, hidden)
    mask = tf.cast(attention_mask, tf.float32)
    mask_expanded = tf.expand_dims(mask, -1)  # (batch, seq_len, 1)
    summed = tf.reduce_sum(token_embeddings * mask_expanded, axis=1)
    counts = tf.clip_by_value(tf.reduce_sum(mask_expanded, axis=1), 1e-9, tf.float32.max)
    return summed / counts


def encode_sentences(sentences, batch_size=32):
    """Encode a list of strings into normalized sentence embeddings using
    the TF embedding model, mirroring SentenceTransformer.encode()."""
    all_embeddings = []
    for i in range(0, len(sentences), batch_size):
        batch = sentences[i:i + batch_size]
        encoded = embed_tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors='tf'
        )
        output = embed_model(**encoded)
        pooled = mean_pooling(output, encoded['attention_mask'])
        normalized = tf.math.l2_normalize(pooled, axis=1)
        all_embeddings.append(normalized.numpy())
    return np.vstack(all_embeddings)


# Precompute movie embeddings once at startup
movie_embeddings = encode_sentences(df["Plot Summary"].tolist())


# Predict emotion
def predict_emotion(sentence, model, tokenizer, max_length, label_map):
    inputs = tokenizer(
        sentence,
        truncation=True,
        padding='max_length',
        max_length=max_length,
        return_tensors='tf'
    )
    prediction = model(**inputs)
    predicted_label = int(tf.argmax(prediction.logits, axis=-1).numpy()[0])
    return label_map[predicted_label]


# Detect genre
def find_random_movie_by_sentence(sentence, model, tokenizer, max_length, label_map):
    for keyword, genre in manual_map.items():
        if keyword in sentence.lower():
            return genre
    return predict_emotion(sentence, model, tokenizer, max_length, label_map)


# Recommendation
def recommend_movies_sbert(input_synopsis, top_n=5):
    input_embeddings = encode_sentences([input_synopsis])

    similarities = cosine_similarity(
        input_embeddings,
        movie_embeddings
    ).flatten()

    top_indices = similarities.argsort()[-top_n:][::-1]
    recommended_movies = df.iloc[top_indices][
        ["Movie Name", "Plot Summary", "Genres"]
    ]

    predicted_genre = find_random_movie_by_sentence(
        input_synopsis,
        model,
        tokenizer,
        max_length=30,
        label_map={
            0: "Drama",
            1: "Comedy",
            2: "Romance",
            3: "Crime",
            4: "Horror"
        }
    )

    filtered_movies = recommended_movies[
        recommended_movies['Genres'].str.contains(
            predicted_genre, case=False, na=False
        )
    ]

    if not filtered_movies.empty:
        return filtered_movies
    return recommended_movies


# Gradio UI
def gradio_interface(input_synopsis):
    return recommend_movies_sbert(input_synopsis)


iface = gr.Interface(
    fn=gradio_interface,
    inputs="text",
    outputs="dataframe",
    live=True,
    title="🎭 Movie Recommendation",
    description="Tell me about the type of movie you're in the mood for!"
)


iface.launch()