"""ApexPulse Fitness Coach - FastAPI Web Interface & Agent Proxy.

Supports two runtime modes:
1. Local Direct Mode (Default for local development):
   Runs the agent locally using ADK's InMemoryRunner.
2. Deployed A2A Proxy Mode (When AGENT_ENGINE_RESOURCE_NAME is set):
   Forwards chat requests over the A2A protocol to Agent Runtime on Google Cloud.
"""

import asyncio
import base64
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
        for key in ("display_step_summary_card_response", "display_biometrics_summary_card_response", "a2ui_card_json", "a2ui_payload", "a2ui_card", "result", "data", "response"):
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
        json_pattern = re.compile(r"(\[\s*\{[\s\S]*\}\s*\]|\{[\s\S]*\"(?:beginRendering|surfaceUpdate|display_step_summary_card_response|display_biometrics_summary_card_response)\"[\s\S]*\})")
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


from app.agent import (
    create_chat_session,
    save_message_to_session,
    list_chat_sessions,
    get_chat_session_history,
    delete_chat_session,
)


@app.get("/sessions")
async def get_all_sessions(user_id: str = "apex-user"):
    """Fetches all past chat sessions in reverse chronological order."""
    sessions = list_chat_sessions(user_id=user_id)
    return JSONResponse({"sessions": sessions})


@app.post("/sessions")
async def create_new_session(req: Request):
    """Generates a fresh chat session with a unique session_id."""
    body = {}
    try:
        body = await req.json()
    except Exception:
        pass
    user_id = body.get("user_id") or "apex-user"
    title = body.get("title") or "New Chat"
    category = body.get("category") or "General"
    session = create_chat_session(user_id=user_id, title=title, category=category)
    return JSONResponse({"session": session})


@app.get("/sessions/{session_id}")
async def get_single_session(session_id: str, user_id: str = "apex-user"):
    """Loads a specific session's full message history and metadata."""
    session = get_chat_session_history(session_id, user_id=user_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": f"Session '{session_id}' not found"})
    return JSONResponse({"session": session})


@app.delete("/sessions/{session_id}")
async def remove_single_session(session_id: str, user_id: str = "apex-user"):
    """Deletes a chat session from Firestore and active cache."""
    success = delete_chat_session(session_id, user_id=user_id)
    if session_id in local_sessions:
        local_sessions.pop(session_id, None)
    return JSONResponse({"status": "success", "session_id": session_id})


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    images_input = body.get("images") or body.get("images_base64")
    image_base64 = body.get("image") or body.get("image_base64")
    image_mime_type = body.get("mime_type") or body.get("image_mime_type") or "image/jpeg"
    user_id = body.get("user_id") or "apex-user"
    session_id = body.get("session_id")

    # If no session_id provided, create a fresh session document
    if not session_id:
        new_sess = create_chat_session(user_id=user_id, title="New Chat")
        session_id = new_sess["session_id"]

    # Decode optional batch of base64 images into (bytes, mime_type) tuples (max 5 images limit)
    decoded_images: List[Tuple[bytes, str]] = []
    raw_images_list: List[Union[str, Dict]] = []

    if images_input and isinstance(images_input, list):
        raw_images_list.extend(images_input[:5])
    elif image_base64:
        raw_images_list.append({"image": image_base64, "mime_type": image_mime_type})

    for img_item in raw_images_list:
        raw_b64 = ""
        item_mime = "image/jpeg"
        if isinstance(img_item, dict):
            raw_b64 = img_item.get("base64") or img_item.get("image") or ""
            item_mime = img_item.get("mime_type") or img_item.get("mimeType") or "image/jpeg"
        elif isinstance(img_item, str):
            raw_b64 = img_item
            item_mime = "image/jpeg"

        raw_b64 = raw_b64.strip()
        if not raw_b64:
            continue

        if "," in raw_b64:
            header, raw_b64 = raw_b64.split(",", 1)
            if "data:" in header and ";base64" in header:
                detected_mime = header.split("data:")[1].split(";base64")[0]
                if detected_mime:
                    item_mime = detected_mime
        try:
            img_bytes = base64.b64decode(raw_b64)
            if img_bytes:
                decoded_images.append((img_bytes, item_mime))
        except Exception as e:
            print(f"⚠️ Failed to decode base64 batch image: {e}")

    # Strictly enforce 5-image limit
    decoded_images = decoded_images[:5]

    log_snippet = message if message else f"({len(decoded_images)} image{'s' if len(decoded_images) > 1 else ''} attached)"
    print(f"📩 [Chat] Received from '{user_id}' [Session: {session_id}] ({len(decoded_images)} images): {log_snippet}")

    # 1. Persist user message & trigger auto-titling if this is the first message
    user_saved_text = message
    if decoded_images and not message:
        user_saved_text = f"📷 [{len(decoded_images)} Image{'s' if len(decoded_images) > 1 else ''} Attached]"
    save_message_to_session(session_id=session_id, role="user", text=user_saved_text, user_id=user_id)

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

                msg_parts = [Part(root=TextPart(text=message or f"Please analyze {'this attached image' if len(decoded_images) == 1 else f'these {len(decoded_images)} attached images'}."))]
                msg = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.user,
                    parts=msg_parts,
                    context_id=_contexts.get(session_id or user_id),
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
                            _contexts[session_id or user_id] = task.context_id
                    if isinstance(update, TaskArtifactUpdateEvent):
                        got_artifact_update = True
                        parts.extend(_extract_parts(update.artifact.parts))

                if not got_artifact_update and last_task is not None:
                    for artifact in getattr(last_task, "artifacts", None) or []:
                        parts.extend(_extract_parts(artifact.parts))
        else:
            # Local Direct Mode (ADK InMemoryRunner with per-session context)
            from google.genai import types as genai_types
            
            # Ensure fresh session or existing valid ADK session for this session_id
            if session_id not in local_sessions:
                adk_session = await runner.session_service.create_session(
                    app_name=runner.app_name,
                    user_id=user_id
                )
                local_sessions[session_id] = adk_session.id
            
            adk_session_id = local_sessions[session_id]
            
            # Construct content parts: single text prompt + distinct inline data parts for each attached image (up to 5)
            genai_parts = [genai_types.Part.from_text(text=message or "Please analyze the attached image(s) for my fitness, workout, nutrition, form, equipment, or biometrics guidance.")]
            for img_bytes, img_mime in decoded_images:
                genai_parts.append(genai_types.Part.from_bytes(data=img_bytes, mime_type=img_mime))

            user_content = genai_types.Content(
                role="user",
                parts=genai_parts
            )

            accumulated_text = []
            
            async def run_agent():
                async for event in runner.run_async(
                    session_id=adk_session_id,
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

    # 2. Persist agent reply to Firestore chat_sessions
    agent_text_combined = "\n\n".join([p["text"] for p in parts if p.get("kind") == "text" or p.get("text")])
    save_message_to_session(session_id=session_id, role="agent", text=agent_text_combined, user_id=user_id, parts=parts)

    # 3. Retrieve updated session metadata (with auto-generated title and category)
    session_data = get_chat_session_history(session_id, user_id=user_id) or {}
    session_title = session_data.get("title", "New Chat")
    session_category = session_data.get("category", "General")

    print(f"📤 [Chat] Returning {len(parts)} parts to '{user_id}' [Session: {session_id} - '{session_title}' ({session_category})]")
    return JSONResponse({
        "parts": parts,
        "session_id": session_id,
        "title": session_title,
        "category": session_category
    })


# Mount static assets
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 ApexPulse Frontend running at http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
