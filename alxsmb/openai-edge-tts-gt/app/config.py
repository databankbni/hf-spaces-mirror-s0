# config.py

DEFAULT_CONFIGS = {
    # Server settings
    "PORT": 5050,
    "API_KEY": 'your_api_key_here',  # Chave padrão aceita

    # TTS settings
    "DEFAULT_VOICE": 'pt-BR-AntonioNeural',
    "DEFAULT_RESPONSE_FORMAT": 'mp3',
    "DEFAULT_SPEED": 1.0,
    "DEFAULT_LANGUAGE": 'pt-BR',

    # Feature flags
    "REQUIRE_API_KEY": False,
    "REMOVE_FILTER": True,
    "EXPAND_API": True,
    "DETAILED_ERROR_LOGGING": True,
}
