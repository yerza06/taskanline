"""Python-клиент API TasKanLine, общий для CLI и MCP-сервера.

async with TasKanLineClient(base_url, token) as client:
    me = await client.me.get()
    result = await client.tasks.query(workspace_id, filters={...})
"""

from taskanline_sdk._version import __version__
from taskanline_sdk.client import TasKanLineClient, paginate
from taskanline_sdk.errors import (
    ApiError,
    AuthenticationError,
    ConflictError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TasKanLineError,
    ValidationError,
)

__all__ = [
    "ApiError",
    "AuthenticationError",
    "ConflictError",
    "NetworkError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "TasKanLineClient",
    "TasKanLineError",
    "ValidationError",
    "__version__",
    "paginate",
]
