"""SPLX proxy implementation of the AI Guard chat agent.

Implements the splx-proxy-sdk Server contract (open-session / send-message /
close-session). Provider/model/mode are supplied per session via typed
extra_args. See https://pypi.org/project/splx-proxy-sdk/.

Auth: set SPLX_PROXY_API_KEY before startup (the SDK validates the x-api-key
header against it and raises at import time if it is missing).
"""
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Request
from pydantic import BaseModel
from splx_proxy_sdk import (
    CloseSessionRequest,
    CloseSessionResponse,
    NotFoundException,
    OpenSessionRequest,
    OpenSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    Server,
)

from agent_core import build_agent, chat as agent_chat

load_dotenv()


class SessionConfig(BaseModel):
    """Per-session configuration passed via the SDK's extra_args."""
    provider: str = "Anthropic"
    model: str = "claude-haiku-4-5-20251001"
    mode: str = "DAS"          # "DAS" (AI Guard middleware) or "Proxy" (Zscaler reverse proxy)
    inspect_prompt: bool = True
    inspect_response: bool = True


class ChatProxy(Server[SessionConfig]):
    """AI Guard agent exposed through the SPLX proxy SDK."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # session_id -> {"agent", "config"}
        self._sessions: dict[str, dict] = {}

    async def open_session(
        self, request: OpenSessionRequest[SessionConfig], raw: Request
    ) -> OpenSessionResponse:
        """Build an agent for the requested provider/model/mode and start a session."""
        config = request.extra_args or SessionConfig()
        session_id = request.session_id or str(uuid4())
        agent, _ = await build_agent(config.provider, config.model, config.mode)
        self._sessions[session_id] = {"agent": agent, "config": config}
        return OpenSessionResponse(session_id=session_id)

    async def send_message(
        self, request: SendMessageRequest[SessionConfig], raw: Request
    ) -> SendMessageResponse:
        """Send a user message to the session's agent and return the response."""
        session = self._sessions.get(request.session_id)
        if session is None:
            raise NotFoundException(
                details="Session not found. Open one via POST /open-session."
            )
        config: SessionConfig = session["config"]
        response, _ = await agent_chat(
            session["agent"],
            request.message,
            request.session_id,
            inspect_prompt=config.inspect_prompt,
            inspect_response=config.inspect_response,
        )
        return SendMessageResponse(session_id=request.session_id, message=response)

    async def close_session(
        self, request: CloseSessionRequest[SessionConfig], raw: Request
    ) -> CloseSessionResponse:
        """Terminate a session and discard its agent."""
        self._sessions.pop(request.session_id, None)
        return CloseSessionResponse()


app = ChatProxy()


@app.get("/health")
def health():
    return {"status": "ok"}
