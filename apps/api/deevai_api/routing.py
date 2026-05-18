"""APIRouter that serializes response models with camelCase aliases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute


class CamelCaseAPIRoute(APIRoute):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("response_model") is not None:
            kwargs.setdefault("response_model_by_alias", True)
        super().__init__(*args, **kwargs)


class CamelCaseRouter(APIRouter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("route_class", CamelCaseAPIRoute)
        super().__init__(*args, **kwargs)

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        if kwargs.get("response_model") is not None:
            kwargs.setdefault("response_model_by_alias", True)
        super().add_api_route(path, endpoint, **kwargs)
