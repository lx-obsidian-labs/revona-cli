from httpx import Client as HttpxClient, Timeout

from openai import OpenAI

from . import BASE_URL
from .config import get_api_key, load_config


def get_client(api_key: str | None = None, model: str | None = None):
    cfg = load_config()
    key = api_key or get_api_key(cfg)
    model = model or cfg.get("model")
    http_client = HttpxClient(timeout=Timeout(300.0, connect=30.0))
    client = OpenAI(base_url=BASE_URL, api_key=key, http_client=http_client, max_retries=3)
    return client, model
