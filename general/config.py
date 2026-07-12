class EmbClientConfig:
    base_url: str
    model_name: str
    api_key: str

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str,
    ) -> None:
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
