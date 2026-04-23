from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AppConfig
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
from app.providers.credential_store import build_credential_store
from app.providers.activity_capture import DesktopEventCollector, ScreenFrameSampler, SessionArtifactStore
from app.providers.demo_credentials import DemoCredentialResolver
from app.providers.ocr_provider import FallbackOCRProvider, MetadataOCRProvider, OptionalTesseractOCRProvider
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
from app.providers.speech_provider import DisabledWakeWordProvider
from app.repositories.sqlite_repository import KeywordRetrievalEngine, SQLiteSourceRepository, SQLiteTraceLogger


@dataclass
class Container:
    config: AppConfig
    database: Database
    profile_manager: ProfileManager
    provider_registry: ProviderRegistry
    source_ingestion_service: SourceIngestionService
    retrieval_service: RetrievalService
    screen_context_service: ScreenContextService
    region_context_service: RegionContextService
    answer_service: AnswerService
    trace_service: TraceService
    session_service: SessionService
    session_attachment_service: SessionAttachmentService
    activity_recording_service: ActivityRecordingService
    guidance_orchestrator: GuidanceOrchestrator
    wake_word_provider: DisabledWakeWordProvider


def build_container(config: AppConfig) -> Container:
    database = Database(config.db_path)
    credential_store = build_credential_store(config.data_dir)
    profile_loader = JsonProfileConfigLoader(config.profile_config_dir)
    profile_manager = ProfileManager(profile_loader, database, credential_store, config.demo_gateway_url)
    demo_resolver = DemoCredentialResolver(resources_dir=config.resources_dir)
    provider_registry = ProviderRegistry(credential_store, demo_resolver=demo_resolver, data_dir=config.data_dir)

    ocr_provider = FallbackOCRProvider(OptionalTesseractOCRProvider(), MetadataOCRProvider())

    screen_capture_provider = PillowScreenCaptureProvider(config.data_dir)
    region_selection_provider = MockRegionSelectionProvider()
    event_collector = DesktopEventCollector()
    artifact_store = SessionArtifactStore(config.data_dir)
    frame_sampler = ScreenFrameSampler(screen_capture_provider, ocr_provider, event_collector)

    source_repository = SQLiteSourceRepository(database)
    parser_registry = ParserRegistry(
        [
            TextSourceParser(),
            CsvSourceParser(),
            XlsxSourceParser(),
            PdfSourceParser(),
            DocxSourceParser(),
            ImageSourceParser(ocr_provider),
        ]
    )
    source_ingestion_service = SourceIngestionService(source_repository, parser_registry, config.data_dir)
    retrieval_service = RetrievalService(KeywordRetrievalEngine(source_repository), source_repository)

    trace_service = TraceService(SQLiteTraceLogger(database))
    session_service = SessionService()
    screen_context_service = ScreenContextService(screen_capture_provider, ocr_provider)
    region_context_service = RegionContextService(screen_capture_provider, region_selection_provider, ocr_provider)
    activity_recording_service = ActivityRecordingService(
        ActivitySessionManager(
            sampler=frame_sampler,
            artifact_store=artifact_store,
            timeline_assembler=TimelineAssembler(),
            summarizer=ActivitySummarizer(profile_manager, provider_registry),
            trace_service=trace_service,
        )
    )
    guidance_orchestrator = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(provider_registry),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace_service),
    )
    answer_service = AnswerService(
        retrieval_service=retrieval_service,
        profile_manager=profile_manager,
        provider_registry=provider_registry,
        trace_service=trace_service,
        session_service=session_service,
        citation_service=CitationService(),
        web_search_service=WebSearchService(),
        activity_recording_service=activity_recording_service,
        guidance_orchestrator=guidance_orchestrator,
    )
    session_attachment_service = SessionAttachmentService(session_service, parser_registry, config.data_dir)

    return Container(
        config=config,
        database=database,
        profile_manager=profile_manager,
        provider_registry=provider_registry,
        source_ingestion_service=source_ingestion_service,
        retrieval_service=retrieval_service,
        screen_context_service=screen_context_service,
        region_context_service=region_context_service,
        answer_service=answer_service,
        trace_service=trace_service,
        session_service=session_service,
        session_attachment_service=session_attachment_service,
        activity_recording_service=activity_recording_service,
        guidance_orchestrator=guidance_orchestrator,
        wake_word_provider=DisabledWakeWordProvider(),
    )
