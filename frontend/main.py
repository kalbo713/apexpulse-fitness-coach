"""ApexPulse Fitness Coach - FastAPI Web Interface & Agent Proxy.

Supports two runtime modes:
1. Local Direct Mode (Default for local development):
   Runs the agent locally using ADK's InMemoryRunner.
2. Deployed A2A Proxy Mode (When AGENT_ENGINE_RESOURCE_NAME is set):
   Forwards chat requests over the A2A protocol to Agent Runtime on Google Cloud.
"""

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

# Ensure parent directory (containing app/) is in Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from project root or frontend directory
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "project-281bf799-969f-49aa-917")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME")
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")

_A2UI_MIME = "application/json+a2ui"
_contexts: Dict[str, str] = {}

app = FastAPI(title="ApexPulse Fitness & Fasting Coach API")

# Add CORS Middleware to ensure browser fetch never gets blocked
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

runner = None
local_sessions: Dict[str, str] = {}

if not RESOURCE:
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai_types
    from app.agent import root_agent
    runner = InMemoryRunner(agent=root_agent)
    print("✅ Initialized ADK InMemoryRunner in Local Direct Mode")
else:
    import google.auth
    import google.auth.transport.requests
    import httpx
    from a2a.client import ClientConfig, ClientFactory
    from a2a.types import (
        AgentCard,
        FilePart,
        Message,
        Part,
        Role,
        TaskArtifactUpdateEvent,
        TextPart,
        TransportProtocol,
    )

    LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]
    A2A_BASE = (
        f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
        f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
    )
    A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"
    _card: Optional[AgentCard] = None
    _creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    def _auth_headers() -> Dict[str, str]:
        _creds.refresh(google.auth.transport.requests.Request())
        return {
            "Authorization": f"Bearer {_creds.token}",
            "Content-Type": "application/json",
        }

    async def _get_card(client: httpx.AsyncClient) -> AgentCard:
        global _card
        if _card is None:
            resp = await client.get(A2A_CARD_URL)
            resp.raise_for_status()
            card = AgentCard(**resp.json())
            card.url = A2A_BASE
            _card = card
        return _card

    def _extract_parts(parts: list) -> List[Dict]:
        out: List[Dict] = []
        for p in parts:
            root = getattr(p, "root", p)
            if isinstance(root, TextPart) and getattr(root, "text", None):
                clean_text, embedded_a2ui = _separate_text_and_a2ui(root.text)
                if clean_text:
                    out.append({"kind": "text", "text": clean_text})
                for a2ui_item in embedded_a2ui:
                    out.append({"kind": "a2ui", "data": a2ui_item})
            elif getattr(root, "data", None) is not None:
                meta = getattr(root, "metadata", None) or {}
                mime = meta.get("mimeType") if isinstance(meta, dict) else None
                if mime == _A2UI_MIME:
                    out.append({"kind": "a2ui", "data": root.data})
            elif isinstance(root, FilePart):
                uri = getattr(getattr(root, "file", None), "uri", None)
                if uri:
                    out.append({"kind": "text", "text": uri})
        return out


def extract_a2ui_items_from_obj(obj: Any) -> List[Dict]:
    """Recursively extracts A2UI v0.8 messages from nested dictionaries, lists, or JSON strings."""
    if isinstance(obj, str):
        obj_clean = obj.strip()
        if (obj_clean.startswith("{") and obj_clean.endswith("}")) or (obj_clean.startswith("[") and obj_clean.endswith("]")):
            try:
                parsed = json.loads(obj_clean)
                return extract_a2ui_items_from_obj(parsed)
            except Exception:
                pass
        return []
    if isinstance(obj, list):
        items = []
        for item in obj:
            if isinstance(item, dict) and any(k in item for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface")):
                items.append(item)
            else:
                items.extend(extract_a2ui_items_from_obj(item))
        return items
    if isinstance(obj, dict):
        for key in ("display_step_summary_card_response", "a2ui_card_json", "a2ui_payload", "a2ui_card", "result", "data", "response"):
            if key in obj:
                res = extract_a2ui_items_from_obj(obj[key])
                if res:
                    return res
        if any(k in obj for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface")):
            return [obj]
    return []


def _separate_text_and_a2ui(text: str) -> Tuple[str, List[Dict]]:
    """Separates conversational text prose from embedded A2UI JSON message arrays."""
    if not text:
        return "", []

    a2ui_messages = []
    clean_text = text

    # 1. Match code blocks ```...``` containing JSON
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in fence_pattern.finditer(text):
        raw_inside = match.group(1)
        items = extract_a2ui_items_from_obj(raw_inside)
        if items:
            a2ui_messages.extend(items)
            clean_text = clean_text.replace(match.group(0), "").strip()

    # 2. Match raw top-level or inline JSON containing beginRendering or surfaceUpdate
    if not a2ui_messages and ("beginRendering" in text or "surfaceUpdate" in text):
        json_pattern = re.compile(r"(\[\s*\{[\s\S]*\}\s*\]|\{[\s\S]*\"(?:beginRendering|surfaceUpdate|display_step_summary_card_response)\"[\s\S]*\})")
        for match in json_pattern.finditer(text):
            raw_match = match.group(1)
            items = extract_a2ui_items_from_obj(raw_match)
            if items:
                a2ui_messages.extend(items)
                clean_text = clean_text.replace(match.group(0), "").strip()

    return clean_text, a2ui_messages


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"status": "ok", "app": "ApexPulse Fitness Coach"}


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    print(f"❌ Error during request: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"⚠️ Error: {type(exc).__name__}: {exc}"}]
        },
    )


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    print(f"📩 [Chat] Received from '{user_id}': {message}")
    parts: List[Dict] = []

    try:
        if RESOURCE:
            # A2A Proxy Mode
            async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
                card = await _get_card(client)
                factory = ClientFactory(
                    ClientConfig(
                        supported_transports=[
                            TransportProtocol.jsonrpc,
                            TransportProtocol.http_json,
                        ],
                        httpx_client=client,
                    )
                )
                a2a_client = factory.create(card)

                msg = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.user,
                    parts=[Part(root=TextPart(text=message))],
                    context_id=_contexts.get(user_id),
                )

                last_task = None
                got_artifact_update = False
                async for event in a2a_client.send_message(msg):
                    if not isinstance(event, tuple):
                        continue
                    task, update = event
                    if task is not None:
                        last_task = task
                        if getattr(task, "context_id", None):
                            _contexts[user_id] = task.context_id
                    if isinstance(update, TaskArtifactUpdateEvent):
                        got_artifact_update = True
                        parts.extend(_extract_parts(update.artifact.parts))

                if not got_artifact_update and last_task is not None:
                    for artifact in getattr(last_task, "artifacts", None) or []:
                        parts.extend(_extract_parts(artifact.parts))
        else:
            # Local Direct Mode (ADK InMemoryRunner)
            from google.genai import types as genai_types
            
            # Ensure fresh session or existing valid session
            if user_id not in local_sessions:
                session = await runner.session_service.create_session(
                    app_name=runner.app_name,
                    user_id=user_id
                )
                local_sessions[user_id] = session.id
            
            session_id = local_sessions[user_id]
            user_content = genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=message)]
            )

            accumulated_text = []
            
            async def run_agent():
                async for event in runner.run_async(
                    session_id=session_id,
                    user_id=user_id,
                    new_message=user_content
                ):
                    if hasattr(event, "content") and event.content:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                accumulated_text.append(part.text)
                            if hasattr(part, "inline_data") and part.inline_data:
                                blob_bytes = getattr(part.inline_data, "data", b"")
                                blob_str = blob_bytes.decode("utf-8", errors="ignore") if isinstance(blob_bytes, bytes) else str(blob_bytes)
                                if "<a2a_datapart_json>" in blob_str:
                                    try:
                                        json_raw = blob_str.split("<a2a_datapart_json>")[1].split("</a2a_datapart_json>")[0]
                                        parsed = json.loads(json_raw)
                                        items = extract_a2ui_items_from_obj(parsed)
                                        for item in items:
                                            parts.append({"kind": "a2ui", "data": item})
                                    except Exception:
                                        pass

            # Timeout after 120 seconds to accommodate live grounding search calls
            await asyncio.wait_for(run_agent(), timeout=120.0)

            if accumulated_text:
                raw_text_str = "".join(accumulated_text).strip()
                clean_text, embedded_a2ui = _separate_text_and_a2ui(raw_text_str)
                if clean_text:
                    parts.append({"kind": "text", "text": clean_text})
                for a2ui_item in embedded_a2ui:
                    parts.append({"kind": "a2ui", "data": a2ui_item})

    except Exception as e:
        print(f"⚠️ Exception in chat handler: {type(e).__name__}: {e}")
        parts = [{"kind": "text", "text": f"Error: {e}"}]

    if not parts:
        parts = [{"kind": "text", "text": "(The coach completed the turn without a text response. Try asking another question!)"}]

    print(f"📤 [Chat] Returning {len(parts)} parts to '{user_id}'")
    return JSONResponse({"parts": parts})


# Mount static assets
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 ApexPulse Frontend running at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
