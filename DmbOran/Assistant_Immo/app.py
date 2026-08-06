import gradio as gr
import os
from qdrant_client import QdrantClient
import requests
from groq import Groq
import json
import re
import unicodedata
from datetime import datetime
from typing import Tuple, List, Dict, Optional, Any


# --- Configuration ---
QDRANT_URL = "https://f1db4954-34db-4b00-b9bb-8acf74c1d6e4.eu-central-1-0.aws.cloud.qdrant.io"
QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

DB_Server = os.getenv("DB_Server")
DB_User = os.getenv("DB_User")
DB_Password = os.getenv("DB_Password")
DB_Name = os.getenv("DB_Name")


# =============================================================================
# ADVANCED TOPIC CLASSIFICATION & FILTERING
# =============================================================================

class TopicClassifier:
    """
    Advanced topic classifier to ensure the chatbot stays on-topic.
    Uses keyword matching + semantic understanding to filter off-topic queries.
    """
    
    # Allowed domains - Real estate in Algeria
    ALLOWED_TOPICS = {
        "real_estate_search": [
            "appartement", "maison", "terrain", "villa", "studio", "duplex", "local",
            "f1", "f2", "f3", "f4", "f5", "f6", "logement", "habitation", "residence",
            "immeuble", "etage", "chambre", "salon", "cuisine", "salle de bain",
            "garage", "parking", "balcon", "terrasse", "jardin", "cave", "grenier",
            "surface", "superficie", "m2", "m²", "pièces", "pieces"
        ],
        "real_estate_transaction": [
            "acheter", "achat", "vendre", "vente", "louer", "location", "bail",
            "locataire", "propriétaire", "proprietaire", "bailleur", "prix", "budget",
            "négocier", "negocier", "offre", "contre-offre", "compromis", "promesse",
            "signature", "acte", "notaire", "frais", "commission", "honoraires",
            "acompte", "caution", "garantie", "depot", "dépôt", "loyer", "charges"
        ],
        "legal_admin": [
            "document", "papier", "dossier", "formalité", "formalite", "procédure",
            "procedure", "démarche", "demarche", "administration", "mairie", "préfecture",
            "cadastre", "conservation", "hypothèque", "hypotheque", "enregistrement",
            "timbre", "taxe", "impôt", "impot", "fiscalité", "fiscalite", "tva",
            "livret foncier", "acte de propriété", "titre foncier", "permis de construire",
            "certificat", "urbanisme", "zonage", "loi", "réglementation", "reglementation",
            "droit", "juridique", "légal", "legal", "contrat", "clause"
        ],
        "financing": [
            "crédit", "credit", "prêt", "pret", "emprunt", "banque", "financement",
            "taux", "intérêt", "interet", "mensualité", "mensualite", "apport",
            "capacité", "capacite", "endettement", "simulation", "simulateur",
            "assurance", "garantie", "hypothécaire", "hypothecaire", "remboursement"
        ],
        "market_info": [
            "marché", "marche", "immobilier", "investissement", "investir", "rentabilité",
            "rentabilite", "rendement", "prix moyen", "estimation", "évaluation",
            "evaluation", "expertise", "tendance", "évolution", "evolution", "quartier",
            "zone", "secteur", "emplacement", "localisation"
        ],
        "algerian_cities": [
            "alger", "oran", "constantine", "annaba", "blida", "bejaia", "béjaïa",
            "tizi ouzou", "setif", "sétif", "batna", "chlef", "boumerdes", "boumerdès",
            "mostaganem", "relizane", "tlemcen", "sidi bel abbes", "béchar", "bechar",
            "skikda", "ghardaia", "guelma", "tiaret", "msila", "m'sila", "el oued",
            "ouargla", "tipaza", "djelfa", "naama", "médea", "medea", "saida", "saïda",
            "khenchela", "el bayadh", "illizi", "ain temouchent", "aïn temouchent",
            "bordj bou arreridj", "bouira", "algerie", "algérie", "dz"
        ],
        "greetings": [
            "bonjour", "bonsoir", "salut", "hello", "hi", "hey", "coucou", "salam",
            "bonne journée", "bonne soirée", "comment allez", "comment vas", "ça va",
            "ca va", "merci", "au revoir", "à bientôt", "a bientot"
        ]
    }
    
    # Explicitly OFF-TOPIC keywords
    OFF_TOPIC_KEYWORDS = [
        # General off-topic
        "recette", "cuisine", "manger", "restaurant", "football", "sport", "match",
        "film", "musique", "chanson", "jeu", "game", "video", "politique", "élection",
        "president", "gouvernement", "religion", "météo", "meteo", "vacances", "voyage",
        "avion", "train", "voiture", "moto", "vélo", "santé", "sante", "médecin",
        "hôpital", "hopital", "maladie", "covid", "école", "ecole", "université",
        "universite", "examen", "cours", "professeur", "étudiant", "etudiant",
        
        # Tech unrelated
        "programmer", "coder", "javascript", "python", "java", "android", "iphone",
        "ordinateur", "laptop", "téléphone", "telephone", "internet", "wifi",
        
        # Completely unrelated
        "guerre", "armée", "armee", "militaire", "drogue", "arme", "violence",
        "sexe", "pornographie", "gambling", "casino", "pari", "crypto", "bitcoin",
        
        # Other services
        "coiffeur", "dentiste", "avocat", "médecin", "docteur", "plombier",
        "électricien", "electricien", "mécanicien", "mecanicien"
    ]
    
    @classmethod
    def normalize(cls, text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = unicodedata.normalize('NFD', text)
        text = re.sub(r"[\u0300-\u036f]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    @classmethod
    def classify(cls, query: str) -> Tuple[bool, str, float]:
        """
        Classify if query is on-topic for real estate.
        Returns: (is_on_topic, detected_category, confidence_score)
        """
        normalized = cls.normalize(query)
        words = set(normalized.split())
        
        # Check for explicit off-topic keywords
        off_topic_matches = sum(1 for kw in cls.OFF_TOPIC_KEYWORDS if kw in normalized)
        if off_topic_matches >= 2:
            return False, "off_topic", 0.9
        
        # Check for on-topic keywords
        topic_scores = {}
        for category, keywords in cls.ALLOWED_TOPICS.items():
            score = sum(1 for kw in keywords if kw in normalized)
            if score > 0:
                topic_scores[category] = score
        
        if topic_scores:
            best_category = max(topic_scores, key=topic_scores.get)
            confidence = min(topic_scores[best_category] / 3.0, 1.0)
            return True, best_category, confidence
        
        # Ambiguous - check query length and patterns
        if len(words) <= 3:
            # Short queries might be greetings or simple questions
            return True, "general", 0.3
        
        # Default: slightly lean towards allowing (benefit of doubt)
        return True, "unknown", 0.2
    
    @classmethod
    def get_off_topic_response(cls) -> str:
        return (
            "🏠 Je suis un assistant spécialisé exclusivement dans **l'immobilier en Algérie**.\n\n"
            "Je peux vous aider avec :\n"
            "• Recherche de biens (appartements, maisons, terrains, villas...)\n"
            "• Informations sur l'achat, la vente ou la location\n"
            "• Démarches administratives et juridiques\n"
            "• Financement et crédits immobiliers\n"
            "• Prix et tendances du marché algérien\n\n"
            "Votre question semble hors de mon domaine d'expertise. "
            "Pourriez-vous reformuler votre demande en rapport avec l'immobilier ?"
        )


# =============================================================================
# INTENT DETECTION - More granular
# =============================================================================

class IntentDetector:
    """
    Detect user intent for more precise responses.
    """
    
    INTENTS = {
        "greeting": {
            "patterns": ["bonjour", "bonsoir", "salut", "hello", "hi", "hey", "coucou", "salam"],
            "max_words": 5
        },
        "thanks": {
            "patterns": ["merci", "thank", "remercie"],
            "max_words": 10
        },
        "goodbye": {
            "patterns": ["au revoir", "bye", "à bientôt", "a bientot", "bonne journée", "bonne soirée"],
            "max_words": 6
        },
        "property_search": {
            "patterns": ["cherche", "recherche", "trouve", "trouver", "besoin", "veux", "voudrais", 
                        "souhaite", "intéressé", "interesse", "disponible"],
            "requires": ["appartement", "maison", "villa", "terrain", "studio", "f1", "f2", "f3", 
                        "f4", "f5", "duplex", "local", "logement"]
        },
        "price_inquiry": {
            "patterns": ["prix", "coût", "cout", "combien", "budget", "tarif", "estimation"],
            "requires": []
        },
        "procedure_inquiry": {
            "patterns": ["comment", "étape", "etape", "procédure", "procedure", "démarche", 
                        "demarche", "document", "formalité", "formalite", "quoi faire"],
            "requires": []
        },
        "legal_inquiry": {
            "patterns": ["loi", "légal", "legal", "droit", "juridique", "réglementation", 
                        "reglementation", "permis", "autorisation"],
            "requires": []
        },
        "comparison": {
            "patterns": ["différence", "difference", "comparer", "comparaison", "mieux", 
                        "meilleur", "vs", "ou bien", "lequel"],
            "requires": []
        }
    }
    
    @classmethod
    def detect(cls, query: str) -> Tuple[str, float]:
        """
        Detect the primary intent of the query.
        Returns: (intent_name, confidence)
        """
        normalized = TopicClassifier.normalize(query)
        word_count = len(normalized.split())
        
        for intent, config in cls.INTENTS.items():
            patterns = config.get("patterns", [])
            max_words = config.get("max_words", 100)
            requires = config.get("requires", [])
            
            pattern_match = any(p in normalized for p in patterns)
            
            if pattern_match:
                if max_words and word_count > max_words:
                    continue
                if requires and not any(r in normalized for r in requires):
                    continue
                return intent, 0.8
        
        return "general_query", 0.5


# =============================================================================
# RESPONSE TEMPLATES
# =============================================================================

class ResponseTemplates:
    """
    Pre-built responses for common intents.
    """
    
    GREETING = (
        "👋 Bonjour et bienvenue !\n\n"
        "Je suis votre assistant immobilier spécialisé en **Algérie**. "
        "Je suis là pour vous accompagner dans vos projets immobiliers.\n\n"
        "**Comment puis-je vous aider ?**\n"
        "• Rechercher un bien (appartement, maison, terrain...)\n"
        "• Répondre à vos questions sur l'achat ou la location\n"
        "• Expliquer les démarches administratives\n"
        "• Vous informer sur les prix du marché\n\n"
        "N'hésitez pas à me poser votre question ! 😊"
    )
    
    THANKS = (
        "De rien ! Je suis ravi d'avoir pu vous aider. 😊\n\n"
        "N'hésitez pas si vous avez d'autres questions sur l'immobilier en Algérie."
    )
    
    GOODBYE = (
        "Au revoir et bonne continuation dans vos recherches ! 👋\n\n"
        "N'hésitez pas à revenir si vous avez d'autres questions immobilières."
    )
    
    NO_RESULTS = (
        "Je n'ai pas trouvé d'informations correspondant exactement à votre demande "
        "dans notre base de données.\n\n"
        "**Suggestions :**\n"
        "• Essayez avec des critères différents (ville, type de bien, budget)\n"
        "• Consultez notre liste complète de biens : https://jacheteenalgerie.com/liste-des-biens/\n"
        "• Prenez rendez-vous avec un expert : https://jacheteenalgerie.com/prendre-rdv/"
    )


# =============================================================================
# IMPROVED EMBEDDING & SEARCH
# =============================================================================

print("🚀 Initializing Advanced RAG Chatbot...")

def get_embedding_via_voyage_ai(text: str) -> Optional[List[float]]:
    """Get embeddings with error handling and retry logic."""
    url = "https://api.voyageai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": [text],
        "model": "voyage-2"
    }
    
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result and "data" in result and len(result["data"]) > 0:
                return result["data"][0]["embedding"]
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Voyage AI attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                return None
    return None


# Initialize Qdrant client
print("🔗 Connecting to Qdrant...")
qdrant_client = None
try:
    qdrant_client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        check_compatibility=False,
        prefer_grpc=False  # Use REST API to avoid asyncio event loop issues
    )
    collection_info = qdrant_client.get_collection(collection_name="biens")
    print(f"✅ Connected to Qdrant! Collection 'biens' has {collection_info.points_count} documents.")
    collection_info_articles = qdrant_client.get_collection(collection_name="articles")
    print(f"✅ Connected to Qdrant! Collection 'articles' has {collection_info_articles.points_count} documents.")
except Exception as e:
    print(f"❌ Failed to connect to Qdrant: {e}")

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# =============================================================================
# LOGGING & DATABASE
# =============================================================================

def log_interaction(user_message: str, response: str, context: str, 
                   tokens_max: int, temperature: float, top_p: float):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "question": user_message,
        "response": response,
        "context": context[:500] if context else "",
        "tokens_max": tokens_max,
        "temperature": temperature,
        "top_p": top_p,
    }
    try:
        requests.post("https://ee98552a720c.ngrok-free.app/log", json=log_entry, timeout=5)
    except Exception as e:
        print(f"⚠️ Failed to send log: {e}")


def save_chat_to_mysql(question: str, answer: str, source: str):
    """Save Q&A to MySQL database."""
    try:
        if not all([DB_Server, DB_User, DB_Password, DB_Name]):
            return
        
        import pymysql
        connection = pymysql.connect(
            host=DB_Server,
            user=DB_User,
            password=DB_Password,
            database=DB_Name,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                sql = (
                    "INSERT INTO qr_chatbot (question, answer, source, created_at) "
                    "VALUES (%s, %s, %s, %s)"
                )
                cursor.execute(sql, (question or "", answer or "", source or "", datetime.now()))
        finally:
            connection.close()
    except Exception as e:
        print(f"❌ MySQL save error: {e}")


# =============================================================================
# ADVANCED COLLECTION DECISION
# =============================================================================

def decide_collection_intelligently(query: str) -> str:
    """
    Decide which collection to search based on query analysis.
    More efficient than using LLM for every decision.
    """
    normalized = TopicClassifier.normalize(query)
    
    # Property-related keywords -> biens
    property_keywords = [
        "appartement", "maison", "villa", "terrain", "studio", "duplex", "local",
        "f1", "f2", "f3", "f4", "f5", "f6", "pièce", "piece", "chambre", "m2", "m²",
        "superficie", "surface", "louer", "location", "acheter", "achat", "vente",
        "prix", "budget", "dzd", "million", "oran", "alger", "constantine"
    ]
    
    # Article-related keywords -> articles
    article_keywords = [
        "comment", "étape", "etape", "procédure", "procedure", "démarche", "demarche",
        "document", "loi", "droit", "juridique", "conseil", "guide", "fiscalité",
        "fiscalite", "réglementation", "reglementation", "investir", "investissement",
        "quoi faire", "quels sont", "expliquer", "expliquez"
    ]
    
    property_score = sum(1 for kw in property_keywords if kw in normalized)
    article_score = sum(1 for kw in article_keywords if kw in normalized)
    
    if property_score > article_score:
        return "biens"
    elif article_score > property_score:
        return "articles"
    else:
        # Default to biens for ambiguous queries
        return "biens"


def _extract_points_from_qdrant_response(res) -> List[Any]:
    """Extract points from various Qdrant response formats."""
    if not res:
        return []
    if hasattr(res, "points"):
        return res.points or []
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for key in ("result", "points", "data", "hits", "items"):
            v = res.get(key)
            if isinstance(v, list):
                return v
    return []


def _get_payload_from_hit(hit) -> Dict:
    """Extract payload from a search hit."""
    if not hit:
        return {}
    if hasattr(hit, "payload"):
        return hit.payload or {}
    if isinstance(hit, dict):
        return hit.get("payload", {})
    return {}


def retrieve_context(query: str, top_k: int = 8) -> Tuple[str, str]:
    """
    Retrieve relevant context from Qdrant.
    Returns: (context_text, collection_name)
    """
    if not qdrant_client:
        print("❌ Qdrant client not initialized.")
        return "", ""
    
    query_embedding = get_embedding_via_voyage_ai(query)
    if query_embedding is None:
        print("❌ Failed to generate embedding.")
        return "", ""
    
    chosen_collection = decide_collection_intelligently(query)
    print(f"📚 Searching collection: {chosen_collection}")
    
    try:
        # Try query_points first
        res = qdrant_client.query_points(
            collection_name=chosen_collection,
            query=query_embedding,
            limit=top_k * 2,
            with_payload=True,
            with_vectors=False,
        )
        points = _extract_points_from_qdrant_response(res)
    except Exception as e:
        print(f"⚠️ query_points failed: {e}")
        try:
            res = qdrant_client.search(
                collection_name=chosen_collection,
                query_vector=query_embedding,
                limit=top_k * 2,
                with_payload=True,
            )
            points = res if isinstance(res, list) else []
        except Exception as e2:
            print(f"❌ Search failed: {e2}")
            return "", ""
    
    if not points:
        return "", chosen_collection
    
    # Build context from results
    context_parts = []
    for idx, p in enumerate(points[:top_k], 1):
        payload = _get_payload_from_hit(p)
        
        if chosen_collection == "biens":
            titre = payload.get('Titre') or payload.get('titre') or ""
            ville = payload.get('Ville') or payload.get('ville_norm') or ""
            superficie = payload.get('superficie') or payload.get('Superficie') or ""
            pieces = payload.get('pieces') or payload.get('Nombre de pièces') or ""
            prix = payload.get('prix') or payload.get('Prix') or ""
            ref = payload.get('REF') or payload.get('ref') or ""
            url = payload.get('URL') or payload.get('url') or ""
            commodites = payload.get('commodites') or []
            
            parts = [f"**{idx}. {titre}**"] if titre else [f"**{idx}. Bien immobilier**"]
            if ville:
                parts.append(f"📍 Ville: {ville}")
            if superficie:
                parts.append(f"📐 Superficie: {superficie} m²")
            if pieces:
                parts.append(f"🚪 Pièces: {pieces}")
            if prix:
                parts.append(f"💰 Prix: {prix}")
            if commodites and isinstance(commodites, list):
                parts.append(f"✨ Commodités: {', '.join(commodites[:5])}")
            if ref:
                parts.append(f"🔖 Réf: {ref}")
            if url:
                parts.append(f"🔗 Lien: {url}")
            
            context_parts.append("\n".join(parts))
        
        else:  # articles
            titre = payload.get('Titre') or payload.get('titre') or ""
            date_pub = payload.get('Date de Publication') or payload.get('date') or ""
            contenu = payload.get('Contenu Texte') or payload.get('contenu') or ""
            url = payload.get('URL') or payload.get('url') or ""
            
            parts = [f"**Article: {titre}**"] if titre else ["**Article**"]
            if date_pub:
                parts.append(f"📅 Date: {date_pub}")
            if contenu:
                # Truncate long content
                excerpt = contenu[:600] + "..." if len(contenu) > 600 else contenu
                parts.append(f"📝 {excerpt}")
            if url:
                parts.append(f"🔗 Lien: {url}")
            
            context_parts.append("\n".join(parts))
    
    context = "\n\n---\n\n".join(context_parts)
    return context, chosen_collection


# =============================================================================
# LLM QUERY
# =============================================================================

def query_groq_llm(messages: List[Dict], tokens_max: int,
                   temperature: float, top_p: float) -> str:
    """Query Groq LLM and return complete response."""
    if not groq_client:
        print("❌ Groq client not initialized")
        return "❌ Erreur : Service LLM non disponible."

    try:
        print(f"🤖 Calling Groq LLM with {len(messages)} messages...")
        chat_completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-safeguard-20b",
            messages=messages,
            temperature=temperature,
            max_tokens=int(tokens_max),
            top_p=top_p,
            stream=True,
        )

        full_response = ""
        for chunk in chat_completion:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta.content or ""
                full_response += delta

        if not full_response.strip():
            print("⚠️ LLM returned empty response")
            return "Je n'ai pas pu générer une réponse. Veuillez réessayer."

        print(f"✅ LLM response received: {len(full_response)} chars")
        return full_response.strip()
    except Exception as e:
        print(f"❌ LLM Error: {type(e).__name__}: {e}")
        return f"❌ Erreur LLM: {e}"


# =============================================================================
# IMPROVED SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = """Vous êtes un assistant immobilier expert spécialisé EXCLUSIVEMENT en immobilier en Algérie.

RÈGLES STRICTES :
1. Répondez UNIQUEMENT aux questions liées à l'immobilier en Algérie
2. Si une question est hors sujet (cuisine, sport, politique, etc.), refusez poliment et rappelez votre spécialisation
3. Basez vos réponses UNIQUEMENT sur le contexte fourni
4. Si le contexte ne contient pas l'information demandée, dites clairement que vous n'avez pas cette information

FORMAT DE RÉPONSE :
- Soyez concis et direct
- Structurez clairement les informations
- Pour les biens : numérotez-les (1., 2., 3.)
- Mettez en évidence les prix avec 💰
- Incluez les liens sources quand disponibles
- N'inventez JAMAIS de données ou de liens

COMPORTEMENT :
- Ton professionnel mais accessible
- Pas de markdown excessif (évitez ###, ****, etc. sauf pour mettre en valeur)
- Réponses en français
- Pas de commentaires sur votre processus interne"""


# =============================================================================
# MAIN RESPONSE FUNCTION
# =============================================================================

def respond(message: str, tokens_max: int, temperature: float, top_p: float) -> Tuple[str, str]:
    """
    Main response function with topic filtering and intent detection.
    """
    message = message.strip()
    if not message:
        return "Veuillez saisir une question.", ""
    
    # Step 1: Topic Classification
    is_on_topic, category, confidence = TopicClassifier.classify(message)
    
    if not is_on_topic:
        off_topic_response = TopicClassifier.get_off_topic_response()
        log_interaction(message, off_topic_response, "OFF_TOPIC", tokens_max, temperature, top_p)
        try:
            save_chat_to_mysql(message, off_topic_response, "off_topic")
        except:
            pass
        return off_topic_response, "Question hors sujet détectée"
    
    # Step 2: Intent Detection
    intent, intent_confidence = IntentDetector.detect(message)
    
    # Handle simple intents directly
    if intent == "greeting":
        response = ResponseTemplates.GREETING
        log_interaction(message, response, "GREETING", tokens_max, temperature, top_p)
        save_chat_to_mysql(message, response, "greeting")
        return response, ""
    
    if intent == "thanks":
        response = ResponseTemplates.THANKS
        log_interaction(message, response, "THANKS", tokens_max, temperature, top_p)
        save_chat_to_mysql(message, response, "thanks")
        return response, ""
    
    if intent == "goodbye":
        response = ResponseTemplates.GOODBYE
        log_interaction(message, response, "GOODBYE", tokens_max, temperature, top_p)
        save_chat_to_mysql(message, response, "goodbye")
        return response, ""
    
    # Step 3: Retrieve Context
    context, collection = retrieve_context(message, top_k=8)
    
    if not context:
        response = ResponseTemplates.NO_RESULTS
        log_interaction(message, response, "NO_CONTEXT", tokens_max, temperature, top_p)
        save_chat_to_mysql(message, response, "no_results")
        return response, "Aucun résultat trouvé"
    
    # Step 4: Generate Response with LLM
    user_content = f"""Question de l'utilisateur : {message}

Contexte pertinent de notre base de données :

{context}

Répondez de manière précise et structurée en vous basant UNIQUEMENT sur ce contexte."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]
    
    response = query_groq_llm(messages, tokens_max, temperature, top_p)
    
    # Step 5: Add relevant links based on collection
    if collection == "biens":
        response += "\n\n---\n📋 Explorer plus de biens : https://jacheteenalgerie.com/liste-des-biens/"
        response += "\n📅 Besoin d'accompagnement ? : https://jacheteenalgerie.com/nos-offres-immobilier/"
    elif collection == "articles":
        response += "\n\n---\n📅 Besoin d'accompagnement ? : https://jacheteenalgerie.com/nos-offres-immobilier/"
    
    # Step 6: Log and save
    log_interaction(message, response, context[:500], tokens_max, temperature, top_p)
    try:
        save_chat_to_mysql(message, response, collection)
    except Exception as e:
        print(f"⚠️ MySQL save failed: {e}")
    
    return response, context


# =============================================================================
# GRADIO API
# =============================================================================

demo = gr.Interface(
    fn=respond,
    inputs=[
        gr.Textbox(label="question"),
        gr.Number(value=1024, label="tokens_max"),
        gr.Number(value=0.3, label="temperature"),
        gr.Number(value=0.85, label="top_p"),
    ],
    outputs=[
        gr.Textbox(label="response"),
        gr.Textbox(label="context"),
    ],
    api_name="predict",
    concurrency_limit=10  # Allow up to 10 concurrent requests
)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        max_threads=20  # Enable multi-threading for concurrent requests
    )