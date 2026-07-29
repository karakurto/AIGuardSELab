import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent_core import build_agent, chat as agent_chat

load_dotenv()

app = FastAPI(title="AI Guard Chat API", version="1.0.0")

# Active sessions: thread_id -> {"agent", "provider", "model", "mode"}.
# An agent is built when a session is opened and discarded when it is closed.
_sessions: dict[str, dict] = {}


class OpenSessionRequest(BaseModel):
    provider: str = "Anthropic"
    model: str = "claude-haiku-4-5-20251001"
    mode: str = "DAS"          # "DAS" (AI Guard middleware) or "Proxy" (Zscaler reverse proxy)


class OpenSessionResponse(BaseModel):
    thread_id: str


class CloseSessionRequest(BaseModel):
    thread_id: str


class CloseSessionResponse(BaseModel):
    status: str
    thread_id: str


class ChatRequest(BaseModel):
    message: str
    thread_id: str            # required — obtained from /v1/sessions/open
    inspect_prompt: bool = True
    inspect_response: bool = True


class ChatResponse(BaseModel):
    response: str
    thread_id: str


@app.post("/v1/sessions/open", response_model=OpenSessionResponse)
async def open_session(req: OpenSessionRequest):
    """Create an agent for the given provider/model/mode and return its session id."""
    try:
        agent, _ = await build_agent(req.provider, req.model, req.mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    thread_id = str(uuid.uuid4())
    _sessions[thread_id] = {
        "agent": agent,
        "provider": req.provider,
        "model": req.model,
        "mode": req.mode,
    }
    return OpenSessionResponse(thread_id=thread_id)


@app.post("/v1/sessions/close", response_model=CloseSessionResponse)
async def close_session(req: CloseSessionRequest):
    """Terminate a session and discard its agent."""
    if _sessions.pop(req.thread_id, None) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return CloseSessionResponse(status="closed", thread_id=req.thread_id)


@app.post("/v1/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Send a message to an open session's agent."""
    session = _sessions.get(req.thread_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Open one via POST /v1/sessions/open.",
        )
    try:
        response, _ = await agent_chat(
            session["agent"],
            req.message,
            req.thread_id,
            inspect_prompt=req.inspect_prompt,
            inspect_response=req.inspect_response,
        )
        return ChatResponse(response=response, thread_id=req.thread_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
