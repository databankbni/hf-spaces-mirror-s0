import logging
from typing import Optional, Any
from google.cloud import firestore
from google.oauth2 import service_account
from utils.credentials import credential_pool, CredentialType

logger = logging.getLogger("DATABASE")

_db_client: Optional[firestore.AsyncClient] = None

def get_firestore_client() -> firestore.AsyncClient:
    """
    Initializes and returns a singleton Async Firestore client.
    Discovers credentials from the Credential Pool or falls back to ADC.
    """
    global _db_client
    if _db_client is not None:
        return _db_client

    logger.database("Initializing Async Firestore database connection...")
    
    cred = credential_pool.get_healthy_credential(CredentialType.FIREBASE_CREDENTIALS)
    
    try:
        if cred and isinstance(cred.value, dict):
            logger.database(f"Using discovered Firestore credentials ({cred.name}).")
            google_creds = service_account.Credentials.from_service_account_info(cred.value)
            project_id = cred.value.get("project_id")
            _db_client = firestore.AsyncClient(credentials=google_creds, project=project_id)
            credential_pool.report_success(cred)
        else:
            logger.database("No explicit Firebase credentials found in pool. Falling back to Application Default Credentials (ADC).")
            _db_client = firestore.AsyncClient()
            
        logger.success("Async Firestore client successfully initialized.")
        return _db_client
    except Exception as e:
        logger.error(f"Failed to initialize Async Firestore client: {e}")
        if cred:
            credential_pool.report_failure(cred, str(e))
        raise RuntimeError("Async Firestore connection failed. Please check your credentials.") from e
