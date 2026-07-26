from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class AsterToolDeclaration:
    name: str
    description: str
    args_schema: type[BaseModel]
    return_schema: type[BaseModel]


@dataclass(frozen=True)
class AsterTool:
    declaration: AsterToolDeclaration
    func: Callable[..., object]

    def invoke(
        self,
        arguments: dict[str, object],
    ) -> BaseModel:
        args = self.declaration.args_schema.model_validate(
            arguments
        )
        result = self.func(args)
        return self.declaration.return_schema.model_validate(
            result
        )


__all__ = ["AsterTool", "AsterToolDeclaration"]
