from pydantic import BaseModel

from arca_mcp.errors import ArcaErrorCause


class WsaaToken(BaseModel):
    token: str
    sign: str
    generation_time: str
    expiration_time: str


class SetupCheckResult(BaseModel):
    ok: bool
    cause: ArcaErrorCause | None = None
    message: str | None = None
    token: WsaaToken | None = None
