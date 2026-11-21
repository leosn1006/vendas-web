"""Cliente Redis único do processo (o from_url cria um pool de conexões — não recriar a cada chamada)."""
import os

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        import redis
        _cliente = redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'), decode_responses=True)
    return _cliente
