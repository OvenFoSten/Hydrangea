from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class AsterToolDeclaration:
    name: str
    description: str
    args_schema: type[BaseModel]
    reply_schema: type[BaseModel]  # Reply content sent back to the model.


@dataclass(frozen=True)
class AsterTool:
    declaration: AsterToolDeclaration
    func: Callable[..., object]  # Receives an args_schema-derived BaseModel.

    def invoke(
        self,
        arguments: dict[str, object],
    ) -> object:
        args = self.declaration.args_schema.model_validate(
            arguments
        )
        return self.func(args)

    def validate_reply(
        self,
        content: object,
    ) -> BaseModel:
        return self.declaration.reply_schema.model_validate(
            content
        )


__all__ = ["AsterTool", "AsterToolDeclaration"]
