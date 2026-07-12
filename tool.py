from collections.abc import Callable
from pydantic import BaseModel


class AsterTool:
    name: str
    description: str
    func: Callable[..., object]
    args_schema: type[BaseModel]
    return_schema: type[BaseModel]

    def __init__(self,
                name: str,
                description: str,
                func: Callable[..., object],
                args_schema: type[BaseModel],
                return_schema: type[BaseModel],) -> None:
        self.name = name
        self.description = description
        self.func = func
        self.args_schema = args_schema
        self.return_schema = return_schema

    def invoke(self, arguments: dict[str, object],) -> BaseModel:
        args = self.args_schema.model_validate(arguments)
        result = self.func(args)
        return self.return_schema.model_validate(result)