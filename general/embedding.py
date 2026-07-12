from openai import OpenAI

from .config import EmbClientConfig

class EmbClient:
    config: EmbClientConfig
    _client: OpenAI

    def __init__(self, config: EmbClientConfig) -> None:
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    def emb(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            model=self.config.model_name,
            input=text,
        )
        if not response.data:
            raise ValueError("Embedding provider returned no embedding.")
        return response.data[0].embedding

    def emb_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._client.embeddings.create(
            model=self.config.model_name,
            input=texts,
        )
        embeddings = [
            item.embedding
            for item in sorted(response.data, key=lambda item: item.index)
        ]
        if len(embeddings) != len(texts):
            raise ValueError(
                "Embedding provider returned an unexpected number of embeddings."
            )
        return embeddings
