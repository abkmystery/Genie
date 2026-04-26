from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import re

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import load_config
from app.core.container import build_container
from app.providers.openai_compatible import OpenAICompatibleClient
from app.models.contracts import (
    AttachmentRecord,
    ActivityStatusResponse,
    ChatRequest,
    CredentialPayload,
    GuidedTaskActionRequest,
    GuidedTaskStatus,
    HealthStatus,
    ProviderDiagnostics,
    SetProfileRequest,
    StartGuidedTaskRequest,
    StartGuidedTaskResponse,
    StartActivityRecordingRequest,
    StartActivityRecordingResponse,
    SpeechToTextRequest,
    StartupProfileRequest,
    StopGuidedTaskRequest,
    StopGuidedTaskResponse,
    StopActivityRecordingRequest,
    StopActivityRecordingResponse,
    TextToSpeechRequest,
    UpdateSettingsRequest,
)


config = load_config()
container = build_container(config)
app = FastAPI(title="Genie Local API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "app://genie",
        "file://",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    profile = container.profile_manager.load_active_profile()
    warnings = []
    if container.profile_manager.credential_store.warning:
        warnings.append(container.profile_manager.credential_store.warning)

    demo_status = None
    provider_diagnostics = ProviderDiagnostics(
        provider_status="unknown",
        provider_source=profile.backend_base_url,
        live_model_name=profile.model_name,
    )
    if profile.id == "demo" and container.provider_registry.demo_resolver is not None:
        if profile.api_style == "genie_gateway":
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    response = await client.get(f"{profile.backend_base_url.rstrip('/')}/health")
                    response.raise_for_status()
                    gateway_health = response.json()
                live = bool(gateway_health.get("has_gemini_api_key"))
                provider_diagnostics = ProviderDiagnostics(
                    provider_status="live_gemma" if live else "fallback_mock",
                    provider_source="demo_gateway",
                    live_model_name=str(gateway_health.get("model") or profile.model_name),
                    fallback_reason=None if live else "Demo gateway is reachable but has no upstream Gemma key configured.",
                )
            except Exception as exc:
                provider_diagnostics = ProviderDiagnostics(
                    provider_status="endpoint_error",
                    provider_source="demo_gateway",
                    live_model_name=profile.model_name,
                    last_model_error=f"{type(exc).__name__}: {exc}",
                )
        else:
            resolved = await container.provider_registry.demo_resolver.resolve(
                demo_source_order=profile.demo_source_order,
                remote_demo_file_url=profile.remote_demo_file_url,
                remote_demo_file_format=profile.remote_demo_file_format,
                default_base_url=(profile.backend_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"),
                default_model=(profile.default_model or profile.model_name or "gemma-4-26b-a4b-it"),
                default_timeout_ms=profile.timeout_ms or 60000,
            )
            demo_status = resolved.status.model_dump()
            provider_diagnostics = ProviderDiagnostics(
                provider_status="live_gemma" if resolved.status.api_key_present else "fallback_mock",
                provider_source=resolved.status.source,
                live_model_name=resolved.status.model,
                fallback_reason=None if resolved.status.api_key_present else "No bundled/remote demo credential found.",
            )

    return HealthStatus(
        ok=True,
        profile=profile,
        storage_mode=container.profile_manager.credential_store.mode,
        warnings=warnings,
        demo_status=demo_status,
        provider_diagnostics=provider_diagnostics,
    )


@app.get("/profiles")
def list_profiles():
    return container.profile_manager.list_profiles()


@app.post("/profiles/resolve-startup")
def resolve_startup_profile(request: StartupProfileRequest):
    return container.profile_manager.resolve_startup_profile(request.profile_id)


@app.post("/profiles/active")
def set_active_profile(request: SetProfileRequest):
    return container.profile_manager.set_active_profile(request.profile_id)


@app.get("/settings")
def get_settings():
    return container.profile_manager.get_settings()


@app.post("/settings")
def update_settings(request: UpdateSettingsRequest):
    return container.profile_manager.update_settings(
        active_profile_id=request.active_profile_id,
        tts_enabled=request.tts_enabled,
        screen_share_enabled=request.screen_share_enabled,
        activity_recording_enabled=request.activity_recording_enabled,
        activity_sampling_hz=request.activity_sampling_hz,
        activity_max_duration_seconds=request.activity_max_duration_seconds,
        guided_task_enabled=request.guided_task_enabled,
        guided_overlay_style=request.guided_overlay_style,
        guided_auto_advance_sensitivity=request.guided_auto_advance_sensitivity,
        guided_completion_mode=request.guided_completion_mode,
        guided_max_planning_steps=request.guided_max_planning_steps,
        guided_show_debug_labels=request.guided_show_debug_labels,
        custom_endpoint=request.custom_endpoint,
        local_endpoint=request.local_endpoint,
        local_model=request.local_model,
        local_model_path=request.local_model_path,
        custom_model=request.custom_model,
        demo_model=request.demo_model,
        onboarding_complete=request.onboarding_complete,
    )


@app.post("/settings/credentials")
def save_credentials(payload: CredentialPayload):
    secrets = {"token": payload.token or ""}
    if payload.endpoint:
        container.profile_manager.update_settings(custom_endpoint=payload.endpoint)
    container.profile_manager.credential_store.save(payload.provider_id, secrets)
    return {"ok": True, "mode": container.profile_manager.credential_store.mode}


@app.delete("/settings/credentials/{provider_id}")
def delete_credentials(provider_id: str):
    container.profile_manager.credential_store.delete(provider_id)
    return {"ok": True}


@app.get("/sources")
def list_sources():
    return container.source_ingestion_service.list_sources()


@app.post("/sources")
async def add_sources(files: list[UploadFile] = File(...)):
    added = []
    for file in files:
        suffix = Path(file.filename or "upload.bin").suffix
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(await file.read())
            temp_path = Path(temp.name)
        try:
            source = container.source_ingestion_service.ingest_file(temp_path, original_filename=file.filename)
            added.append(source)
        finally:
            if temp_path.exists():
                temp_path.unlink()
    return added


@app.post("/sources/{source_id}/reindex")
def reindex_source(source_id: str):
    try:
        return container.source_ingestion_service.reindex_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/sources/{source_id}")
def delete_source(source_id: str):
    container.source_ingestion_service.remove_source(source_id)
    return {"ok": True}


@app.get("/sessions/{conversation_id}/attachments", response_model=list[AttachmentRecord])
def list_attachments(conversation_id: str):
    return container.session_attachment_service.list(conversation_id)


@app.post("/sessions/{conversation_id}/attachments", response_model=list[AttachmentRecord])
async def add_attachments(conversation_id: str, files: list[UploadFile] = File(...)):
    upload_paths: list[tuple[Path, str | None]] = []
    for file in files:
        suffix = Path(file.filename or "upload.bin").suffix
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(await file.read())
            temp_path = Path(temp.name)
        upload_paths.append((temp_path, file.filename))

    try:
        return container.session_attachment_service.add_files(conversation_id, upload_paths)
    finally:
        for temp_path, _ in upload_paths:
            if temp_path.exists():
                temp_path.unlink()


@app.delete("/sessions/{conversation_id}/attachments/{attachment_id}")
def delete_attachment(conversation_id: str, attachment_id: str):
    container.session_attachment_service.delete(conversation_id, attachment_id)
    return {"ok": True}


@app.post("/screen/capture")
def capture_screen():
    context = container.screen_context_service.capture()
    return context


@app.get("/captures/{capture_id}")
def get_capture(capture_id: str):
    capture_id = capture_id.removesuffix(".png")
    if not re.fullmatch(r"[0-9a-fA-F\\-]{36}", capture_id):
        raise HTTPException(status_code=400, detail="Invalid capture id")
    path = container.config.data_dir / "captures" / f"{capture_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Capture not found")
    return FileResponse(str(path), media_type="image/png")


@app.post("/screen/region")
def capture_region(request: ChatRequest):
    if not request.region_selection:
        raise HTTPException(status_code=400, detail="region_selection is required")
    base_capture = container.screen_context_service.get_last_capture()
    if base_capture is None:
        base_capture = container.screen_context_service.capture().capture
    return container.region_context_service.capture_region(base_capture, request.region_selection)


@app.post("/audio/transcribe")
async def transcribe_audio(request: SpeechToTextRequest):
    profile = container.profile_manager.load_active_profile()
    provider = container.provider_registry.create_speech_to_text_client(profile)
    try:
        text = await provider.transcribe(
            audio_base64=request.audio_base64,
            audio_format=request.audio_format,
            transcript_hint=request.transcript_hint,
        )
    except Exception as exc:
        return {
            "text": "",
            "error": str(exc),
            "provider": provider.diagnostics(),
        }
    return {"text": text}


@app.post("/audio/speak")
async def speak_text(request: TextToSpeechRequest):
    profile = container.profile_manager.load_active_profile()
    provider = container.provider_registry.create_text_to_speech_client(profile)
    try:
        return await provider.speak(request.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/audio/stop")
async def stop_speaking():
    profile = container.profile_manager.load_active_profile()
    provider = container.provider_registry.create_text_to_speech_client(profile)
    try:
        return await provider.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/activity/start", response_model=StartActivityRecordingResponse)
def start_activity_recording(request: StartActivityRecordingRequest):
    settings = container.profile_manager.get_settings()
    if not settings.activity_recording_enabled:
        return StartActivityRecordingResponse(ok=False, session=None, message="Activity recording is disabled in Settings.")
    duration_seconds = min(
        max(5, request.duration_seconds),
        settings.activity_max_duration_seconds or request.duration_seconds,
    )
    sampling_hz = request.sampling_hz or settings.activity_sampling_hz or 1.0
    return container.activity_recording_service.start(duration_seconds=duration_seconds, sampling_hz=sampling_hz)


@app.post("/activity/stop", response_model=StopActivityRecordingResponse)
def stop_activity_recording(request: StopActivityRecordingRequest):
    return container.activity_recording_service.stop(session_id=request.session_id)


@app.get("/activity/current", response_model=ActivityStatusResponse)
def get_current_activity():
    return container.activity_recording_service.current()


@app.get("/activity/last", response_model=ActivityStatusResponse)
def get_last_activity():
    return container.activity_recording_service.last()


@app.post("/activity/summarize", response_model=StopActivityRecordingResponse)
def summarize_last_activity(request: StopActivityRecordingRequest):
    summary = container.activity_recording_service.summarize(session_id=request.session_id)
    if summary is None:
        return StopActivityRecordingResponse(ok=False, session=None, summary=None, message="No completed recording is available to summarize.")
    status = container.activity_recording_service.last().last
    return StopActivityRecordingResponse(ok=True, session=status, summary=summary, message="Summary loaded.")


def _capture_guided_context(region_selection=None):
    screen_context = container.screen_context_service.capture()
    region_context = None
    if region_selection:
        region_context = container.region_context_service.capture_region(screen_context.capture, region_selection)
    return screen_context, region_context


@app.post("/guided/start", response_model=StartGuidedTaskResponse)
async def start_guided_task(request: StartGuidedTaskRequest):
    settings = container.profile_manager.get_settings()
    if not settings.guided_task_enabled:
        return StartGuidedTaskResponse(ok=False, status=None, message="Guided Task mode is disabled in Settings.")
    screen_context, region_context = _capture_guided_context(request.region_selection)
    conversation_id = container.session_service.ensure_conversation(request.conversation_id)
    evidence = container.retrieval_service.retrieve_evidence(request.prompt, request.source_ids or None)
    provider = container.provider_registry.create_model_client(container.profile_manager.load_active_profile())
    return await container.guidance_orchestrator.start(
        goal=request.prompt,
        conversation_id=conversation_id,
        screen_context=screen_context,
        region_context=region_context,
        evidence=evidence,
        profile=container.profile_manager.load_active_profile(),
        provider=provider,
        max_steps=settings.guided_max_planning_steps or 6,
        overlay_style=settings.guided_overlay_style or "arrow_pulse",
    )


@app.get("/guided/current", response_model=GuidedTaskStatus)
def get_guided_task_status():
    return container.guidance_orchestrator.current()


@app.post("/guided/observe", response_model=GuidedTaskStatus)
async def observe_guided_task():
    settings = container.profile_manager.get_settings()
    screen_context, region_context = _capture_guided_context()
    profile = container.profile_manager.load_active_profile()
    return await container.guidance_orchestrator.observe(
        screen_context=screen_context,
        region_context=region_context,
        profile=profile,
        provider=container.provider_registry.create_model_client(profile),
        completion_mode=settings.guided_completion_mode or "conservative",
        auto_advance_sensitivity=settings.guided_auto_advance_sensitivity or 0.85,
        overlay_style=settings.guided_overlay_style or "arrow_pulse",
    )


@app.post("/guided/action", response_model=GuidedTaskStatus)
async def guided_task_action(request: GuidedTaskActionRequest):
    settings = container.profile_manager.get_settings()
    profile = container.profile_manager.load_active_profile()
    provider = container.provider_registry.create_model_client(profile)
    if request.action == "pause":
        return container.guidance_orchestrator.pause(True)
    if request.action == "resume":
        return container.guidance_orchestrator.pause(False)
    if request.action == "cant_find_it":
        return container.guidance_orchestrator.cant_find_it()

    screen_context, region_context = _capture_guided_context(request.region_selection)
    if request.action in {"mark_done", "next_step"}:
        return await container.guidance_orchestrator.confirm_step(
            overlay_style=settings.guided_overlay_style or "arrow_pulse",
            screen_context=screen_context,
            profile=profile,
            provider=provider,
            region_context=region_context,
        )
    if request.action == "rescan":
        return await container.guidance_orchestrator.rescan(
            overlay_style=settings.guided_overlay_style or "arrow_pulse",
            screen_context=screen_context,
            profile=profile,
            provider=provider,
            region_context=region_context,
        )
    raise HTTPException(status_code=400, detail="Unsupported guided task action.")


@app.post("/guided/stop", response_model=StopGuidedTaskResponse)
def stop_guided_task(request: StopGuidedTaskRequest):
    return container.guidance_orchestrator.stop()


@app.post("/chat")
async def chat(request: ChatRequest):
    screen_context = container.screen_context_service.capture() if request.use_current_screen else None
    region_context = None
    if request.use_region:
        base_capture = container.screen_context_service.get_last_capture()
        if base_capture is None:
            base_capture = container.screen_context_service.capture().capture
        if request.region_selection:
            region_context = container.region_context_service.capture_region(base_capture, request.region_selection)
    return await container.answer_service.answer(request, screen_context=screen_context, region_context=region_context)


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    return container.trace_service.list_events(trace_id)


@app.post("/diagnostics/run")
async def run_diagnostics():
    """
    Basic diagnostics to help users validate their current profile configuration.
    Does not expose secrets.
    """
    profile = container.profile_manager.load_active_profile()
    result: dict[str, object] = {"ok": True, "profile_id": profile.id, "transport": profile.transport, "model": profile.model_name}
    stt_provider = container.provider_registry.create_speech_to_text_client(profile)
    tts_provider = container.provider_registry.create_text_to_speech_client(profile)
    activity_status = container.activity_recording_service.current()
    result["speech_to_text"] = stt_provider.diagnostics()
    result["text_to_speech"] = tts_provider.diagnostics()
    result["activity_capture"] = {
        "enabled": container.profile_manager.get_settings().activity_recording_enabled,
        "current_session": activity_status.current.model_dump() if activity_status.current else None,
        "last_session": activity_status.last.model_dump() if activity_status.last else None,
    }
    result["guided_task"] = container.guidance_orchestrator.current().model_dump()

    if profile.id == "demo" and container.provider_registry.demo_resolver is not None:
        resolved = await container.provider_registry.demo_resolver.resolve(
            demo_source_order=profile.demo_source_order,
            remote_demo_file_url=profile.remote_demo_file_url,
            remote_demo_file_format=profile.remote_demo_file_format,
            default_base_url=(profile.backend_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"),
            default_model=(profile.default_model or profile.model_name or "gemma-4-26b-a4b-it"),
            default_timeout_ms=profile.timeout_ms or 60000,
        )
        result["demo_source"] = resolved.status.source
        result["demo_config_detected"] = resolved.status.api_key_present
        result["demo_model"] = resolved.status.model
        if not resolved.api_key:
            result["ok"] = True
            result["message"] = "Demo config not present; using offline fallback."
            return result
        try:
            client = OpenAICompatibleClient(
                base_url=resolved.status.base_url,
                bearer_token=resolved.api_key,
                timeout_s=max(5, resolved.status.timeout_ms / 1000),
            )
            # Simple ping by issuing a minimal chat request.
            text = await client.chat_completions(
                {
                    "model": resolved.status.model,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                    "temperature": 0,
                }
            )
            result["message"] = "Demo provider reachable."
            result["sample_reply"] = (text or "")[:120]
            return result
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "profile_id": profile.id}

    # Local/custom HTTP profiles: attempt an OpenAI-compatible /models check when possible.
    endpoint = (profile.endpoint_override or profile.backend_base_url or "").rstrip("/")
    if not endpoint:
        return {"ok": False, "error": "No endpoint configured for this profile.", "profile_id": profile.id}

    token = container.profile_manager.credential_store.get(profile.id) or {}
    headers = {}
    if token.get("token"):
        headers["Authorization"] = f"Bearer {token['token']}"

    try:
        async with httpx.AsyncClient(timeout=max(5, profile.timeout_ms / 1000)) as client:
            resp = await client.get(f"{endpoint}/models", headers=headers)
            result["status_code"] = resp.status_code
            if resp.status_code >= 400:
                return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}", "profile_id": profile.id}
            data = resp.json()
        models = data.get("data") or []
        ids = [m.get("id") for m in models if isinstance(m, dict)]
        result["message"] = "Endpoint reachable."
        result["models_count"] = len(ids)
        result["configured_model_visible"] = profile.model_name in ids
        return result
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "profile_id": profile.id}
