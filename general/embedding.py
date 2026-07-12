from openai import OpenAI

from .config import EmbClientConfig

_BGE_M3_CONFIG = EmbClientConfig(
    base_url="http://127.0.0.1:8001/v1",
    model_name="BAAI/bge-m3",
    api_key="EMPTY",
)

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


if __name__ == "__main__":
    client = EmbClient(_BGE_M3_CONFIG)

    single_embedding = client.emb("Aster embedding smoke test")
    batch_embeddings = client.emb_batch([
        "The first batch item.",
        "The second batch item.",
    ])

    if not single_embedding:
        raise AssertionError("Smoke test failed: single embedding is empty.")
    if len(batch_embeddings) != 2:
        raise AssertionError("Smoke test failed: batch size does not match.")
    if any(
        len(embedding) != len(single_embedding)
        for embedding in batch_embeddings
    ):
        raise AssertionError("Smoke test failed: embedding dimensions differ.")

    print("Single embedding dimension:", len(single_embedding))
    print("Batch embedding count:", len(batch_embeddings))
    print("Embedding smoke test passed.")
        
