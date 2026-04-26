from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.database import Database
from app.domain.answer_service import AnswerService
from app.domain.activity_recording_service import ActivityRecordingService, ActivitySessionManager
from app.domain.activity_timeline import ActivitySummarizer, TimelineAssembler
from app.domain.citation_service import CitationService
from app.domain.guidance_orchestrator import GuidanceOrchestrator
from app.domain.guided_task_session_manager import GuidedTaskSessionManager
from app.domain.guided_task_trace_logger import GuidedTaskTraceLogger
from app.domain.profile_service import ProfileManager, ProviderRegistry
from app.domain.recovery_policy import RecoveryPolicy
from app.domain.region_context_service import RegionContextService
from app.domain.retrieval_service import RetrievalService
from app.domain.screen_context_service import ScreenContextService
from app.domain.session_service import SessionService
from app.domain.session_attachment_service import SessionAttachmentService
from app.domain.source_ingestion_service import SourceIngestionService
from app.domain.step_progress_detector import StepProgressDetector
from app.domain.task_planner import TaskPlanner
from app.domain.target_grounder import TargetGrounder
from app.domain.trace_service import TraceService
from app.domain.web_search_service import WebSearchService
from app.models.contracts import ActivityFrameRef, ActivityTimeline, ChatRequest, RegionSelection, ScreenCaptureRef
from app.providers.credential_store import FileCredentialStore
from app.providers.activity_capture import DesktopEventCollector, ScreenFrameSampler, SessionArtifactStore
from app.providers.ocr_provider import MetadataOCRProvider
from app.providers.profile_loader import JsonProfileConfigLoader
from app.providers.screen_capture_provider import MockRegionSelectionProvider, PillowScreenCaptureProvider
from app.providers.source_parsers import (
    CsvSourceParser,
    DocxSourceParser,
    ImageSourceParser,
    ParserRegistry,
    PdfSourceParser,
    TextSourceParser,
    XlsxSourceParser,
)
from app.repositories.sqlite_repository import KeywordRetrievalEngine, SQLiteSourceRepository, SQLiteTraceLogger


def build_services(tmp_path: Path):
    database = Database(tmp_path / "genie.db")
    credential_store = FileCredentialStore(tmp_path / "credentials.json")
    profile_loader = JsonProfileConfigLoader(Path(__file__).resolve().parents[3] / "config" / "profiles")
    profile_manager = ProfileManager(profile_loader, database, credential_store, "http://127.0.0.1:8788")
    provider_registry = ProviderRegistry(credential_store)
    source_repository = SQLiteSourceRepository(database)
    parser_registry = ParserRegistry(
        [
            TextSourceParser(),
            CsvSourceParser(),
            XlsxSourceParser(),
            PdfSourceParser(),
            DocxSourceParser(),
            ImageSourceParser(MetadataOCRProvider()),
        ]
    )
    ingestion = SourceIngestionService(source_repository, parser_registry, tmp_path)
    retrieval = RetrievalService(KeywordRetrievalEngine(source_repository), source_repository)
    trace = TraceService(SQLiteTraceLogger(database))
    capture_provider = PillowScreenCaptureProvider(tmp_path)
    screen = ScreenContextService(capture_provider, MetadataOCRProvider())
    region = RegionContextService(capture_provider, MockRegionSelectionProvider(), MetadataOCRProvider())
    activity = ActivityRecordingService(
        ActivitySessionManager(
            sampler=ScreenFrameSampler(capture_provider, MetadataOCRProvider(), DesktopEventCollector()),
            artifact_store=SessionArtifactStore(tmp_path),
            timeline_assembler=TimelineAssembler(),
            summarizer=ActivitySummarizer(profile_manager, provider_registry),
            trace_service=trace,
        )
    )
    guidance = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(provider_registry),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace),
    )
    session = SessionService()
    answer = AnswerService(retrieval, profile_manager, provider_registry, trace, session, CitationService(), WebSearchService(), activity, guidance)
    attachments = SessionAttachmentService(session, parser_registry, tmp_path)
    return {
        "database": database,
        "credential_store": credential_store,
        "profile_manager": profile_manager,
        "ingestion": ingestion,
        "retrieval": retrieval,
        "answer": answer,
        "attachments": attachments,
        "screen": screen,
        "region": region,
        "activity": activity,
        "guidance": guidance,
    }


def test_profile_resolution_and_settings(tmp_path: Path):
    services = build_services(tmp_path)
    manager = services["profile_manager"]

    resolved = manager.resolve_startup_profile("local")
    assert resolved.id == "local"

    settings = manager.update_settings(tts_enabled=True, custom_endpoint="http://localhost:9999/v1")
    assert settings.tts_enabled is True
    assert settings.custom_endpoint == "http://localhost:9999/v1"


def test_secure_credential_file_store(tmp_path: Path):
    store = FileCredentialStore(tmp_path / "creds.json")
    store.save("custom", {"token": "abc123"})
    assert store.has("custom") is True
    assert store.get("custom") == {"token": "abc123"}
    store.delete("custom")
    assert store.get("custom") is None


def test_source_ingestion_retrieval_and_answer(tmp_path: Path):
    services = build_services(tmp_path)
    source = tmp_path / "benefits.txt"
    source.write_text("Benefits start next month. FastAPI powers Genie.", encoding="utf-8")

    indexed = services["ingestion"].ingest_file(source)
    assert indexed.chunk_count >= 1

    evidence = services["retrieval"].retrieve_evidence("When do benefits start?", [indexed.id])
    assert evidence
    assert "benefits" in (evidence[0].quote or "").lower()

    response = __import__("asyncio").run(
        services["answer"].answer(ChatRequest(prompt="When do benefits start?", source_ids=[indexed.id]))
    )
    assert response.trace_id
    assert response.evidence
    assert "grounded evidence" in response.answer.lower() or "benefits" in response.answer.lower()


def test_screen_and_region_pipeline(tmp_path: Path):
    services = build_services(tmp_path)
    screen_context = services["screen"].capture()
    assert screen_context.capture.width > 0
    assert screen_context.summary

    region_context = services["region"].capture_region(
        screen_context.capture,
        RegionSelection(x=10, y=10, width=100, height=80),
    )
    assert region_context.selection.width == 100
    assert region_context.capture.path


def test_session_attachments_are_grounded_in_answers(tmp_path: Path):
    services = build_services(tmp_path)
    attachment = tmp_path / "one-off.txt"
    attachment.write_text("The launch code is CORAL-7.", encoding="utf-8")

    services["attachments"].add_files("conv-1", [(attachment, "one-off.txt")])
    response = __import__("asyncio").run(
        services["answer"].answer(ChatRequest(prompt="What is the launch code?", conversation_id="conv-1"))
    )
    labels = " ".join(item.label for item in response.evidence)
    assert "Attachment" in labels


def test_activity_session_start_stop_and_summary(tmp_path: Path):
    services = build_services(tmp_path)
    started = services["activity"].start(duration_seconds=5, sampling_hz=1.0)
    assert started.ok is True
    stopped = services["activity"].stop(started.session.id if started.session else None)
    assert stopped.session is not None
    assert stopped.session.status in {"stopped", "completed"}
    assert stopped.summary is not None
    assert stopped.summary.steps


def test_activity_summary_reports_only_action_changes(tmp_path: Path):
    started_at = datetime.now(timezone.utc)
    capture = ScreenCaptureRef(
        id="cap-1",
        path=str(tmp_path / "screen.png"),
        width=1920,
        height=1080,
        mode="simulated",
        captured_at=started_at,
    )
    timeline = ActivityTimeline(
        session_id="activity-1",
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=3),
        total_frames=2,
        representative_frames=[
            ActivityFrameRef(
                id="frame-1",
                capture=capture,
                timestamp=started_at + timedelta(seconds=1),
                window_title="Kaggle: Competitions and Hackathons - Google Chrome",
                ocr_text="kaggle Competitions and Hackathons Search competitions Filters Featured",
            )
        ],
    )

    services = build_services(tmp_path)
    summarizer = ActivitySummarizer(services["profile_manager"], services["answer"].provider_registry)
    steps = summarizer._heuristic_steps(timeline)

    assert steps
    assert "Kaggle: Competitions and Hackathons" in steps[0]
    assert any("competitions filter/search area" in step for step in steps)
    assert all("Image file" not in step and "1920x1080" not in step for step in steps)


def test_answer_service_does_not_claim_history_without_recording(tmp_path: Path):
    services = build_services(tmp_path)
    response = __import__("asyncio").run(
        services["answer"].answer(ChatRequest(prompt="Summarize last recording"))
    )
    assert "don’t have a previous recording" in response.answer or "don't have a previous recording" in response.answer
