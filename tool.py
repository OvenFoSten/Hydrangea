from collections.abc import Callable, Mapping
from typing import Any, Dict, Generic, TypeVar
from pydantic import BaseModel



ArgsT = TypeVar("ArgsT", bound=BaseModel)
ReturnT = TypeVar("ReturnT", bound=BaseModel)
class AsterTool(Generic[ArgsT, ReturnT]):
    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[[ArgsT], ReturnT],
        args_schema: type[ArgsT],
        return_schema: type[ReturnT],
    ) -> None:
        self.name = name
        self.description = description
        self.func = func
        self.args_schema = args_schema
        self.return_schema = return_schema

    def invoke(self, arguments: dict[str, object]) -> ReturnT:
        args = self.args_schema.model_validate(arguments)
        result = self.func(args)
        return self.return_schema.model_validate(result)