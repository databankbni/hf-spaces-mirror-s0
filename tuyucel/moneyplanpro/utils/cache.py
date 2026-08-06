import time

class SimpleCache:
    def __init__(self):
        self._cache = {}
        self._timestamps = {}

    def get(self, key: str):
        """Veriyi getir, süresi dolmuşsa None dön"""
        if key in self._cache:
            if time.time() < self._timestamps.get(key, 0):
                return self._cache[key]
            else:
                # Süre dolmuş, temizle
                del self._cache[key]
                del self._timestamps[key]
        return None

    def set(self, key: str, value: any, ttl_seconds: int = 60):
        """Veriyi kaydet"""
        self._cache[key] = value
        self._timestamps[key] = time.time() + ttl_seconds

cache = SimpleCache()
