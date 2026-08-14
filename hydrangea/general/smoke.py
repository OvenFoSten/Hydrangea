import os
from pathlib import Path

from dotenv import load_dotenv

from .config import EmbClientConfig
from .embedding import EmbClient


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    client = EmbClient(EmbClientConfig(
        base_url=os.environ["ASTER_EMBED_BASE_URL"],
        model_name=os.environ["ASTER_EMBED_MODEL_NAME"],
        api_key=os.environ["ASTER_EMBED_API_KEY"],
    ))

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


if __name__ == "__main__":
    main()
