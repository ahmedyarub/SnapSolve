"""Antigravity SDK Service — FastAPI wrapper for the Google Antigravity SDK.

Exposes POST /chat with SSE streaming and GET /health.

Usage:
    export GEMINI_API_KEY="your_api_key_here"
    python antigravity_service.py
"""

import asyncio
import base64
import json
import logging
import os

import signal
import sys
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from google.antigravity import Agent, LocalAgentConfig
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("antigravity_service")

# ---------------------------------------------------------------------------
# Agent session management
# ---------------------------------------------------------------------------

_agent: Optional[Agent] = None
_agent_lock = asyncio.Lock()


async def _get_or_create_agent(
    model: Optional[str] = None,
    system_instructions: Optional[str] = None,
    cwd: Optional[str] = None,
) -> Agent:
    """Get the existing agent or create a new one."""
    global _agent

    async with _agent_lock:
        if _agent is None:
            logger.info("Creating new Antigravity agent (model=%s, cwd=%s)", model, cwd)
            config = LocalAgentConfig(
                model=model or "gemini-3.5-flash",
                system_instructions=system_instructions or "",
            )
            _agent = Agent(config)
            await _agent.__aenter__()
            logger.info("Agent created and ready.")
        return _agent


async def _close_agent():
    """Close the current agent session."""
    global _agent

    async with _agent_lock:
        if _agent is not None:
            try:
                await _agent.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing agent: %s", e)
            _agent = None
            logger.info("Agent closed.")



# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Antigravity service starting on port %s", PORT)
    yield
    await _close_agent()
    logger.info("Antigravity service stopped.")


app = FastAPI(title="Antigravity SDK Service", lifespan=lifespan)


class ChatRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    cwd: Optional[str] = None
    system_instructions: Optional[str] = None
    new_session: bool = False
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    """Stream a chat response as SSE (text/event-stream)."""

    async def event_stream():
        try:
            if request.new_session:
                await _close_agent()

            cwd = request.cwd

            # Change working directory for the agent
            if cwd:
                os.chdir(cwd)
                logger.info("Agent working directory: %s", cwd)

            agent = await _get_or_create_agent(
                model=request.model,
                system_instructions=request.system_instructions,
                cwd=cwd,
            )

            logger.info("Chat request: %s", request.prompt[:100])

            # Build the prompt — include image if provided
            if request.image_base64:
                image_bytes = base64.b64decode(request.image_base64)
                ext = (request.image_mime_type or "image/png").split("/")[-1]
                tmp = tempfile.NamedTemporaryFile(
                    suffix=f".{ext}", delete=False
                )
                tmp.write(image_bytes)
                tmp.close()
                logger.info("Image saved to temp file: %s", tmp.name)
                # Pass image path + text prompt together
                chat_input = f"[Image: {tmp.name}]\n{request.prompt}"
            else:
                chat_input = request.prompt

            response = await agent.chat(chat_input)

            async for token in response:
                # SSE format: each event is "data: <payload>\n\n"
                payload = json.dumps({"token": token})
                yield f"data: {payload}\n\n"

            yield "data: [DONE]\n\n"
            logger.info("Chat response complete.")

        except Exception as e:
            logger.exception("Error during chat")
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/reset")
async def reset():
    """Close the current agent and start fresh."""
    await _close_agent()
    return {"status": "reset"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("ANTIGRAVITY_PORT", "8200"))


def _handle_exit(_sig, _frame):
    logger.info("Signal received, exiting.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit)

    uvicorn.run(app, host="0.0.0.0", port=PORT)
