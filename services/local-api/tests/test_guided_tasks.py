from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from app.domain.guidance_orchestrator import GuidanceOrchestrator
from app.domain.guided_task_intent import parse_guided_task_prompt
from app.domain.guided_task_session_manager import GuidedTaskSessionManager
from app.domain.guided_task_trace_logger import GuidedTaskTraceLogger
from app.domain.recovery_policy import RecoveryPolicy
from app.domain.step_progress_detector import StepProgressDetector
from app.domain.task_planner import TaskPlanner
from app.domain.target_grounder import TargetGrounder
from app.domain.trace_service import TraceService
from app.models.contracts import (
    ChatRequest,
    GatewayChatResponse,
    GroundingResult,
    GuidedTaskPlan,
    GuidedTaskStep,
    OverlayTarget,
    ProviderCapabilities,
    ProviderConfig,
    ScreenCaptureRef,
    ScreenContext,
)
from app.repositories.sqlite_repository import SQLiteTraceLogger

from app.core.database import Database
from test_services import build_services


class _StubPlannerProvider:
    async def answer(self, prompt, profile, evidence, screen_context=None, region_context=None, audio_base64=None, audio_format=None, additional_image_paths=None):
        return GatewayChatResponse(
            answer='{"title":"Submit the form","steps":[{"instruction_text":"Click Submit","target_description":"Submit","completion_hint":"Success","grounding_required":true}]}',
            provider_used="stub:model",
        )


def _screen_context(tmp_path: Path, text: str = "Submit Continue Success") -> ScreenContext:
    image_path = tmp_path / "capture.png"
    image_path.write_bytes(b"png")
    capture = ScreenCaptureRef(
        id="capture-1",
        path=str(image_path),
        width=1280,
        height=720,
        mode="simulated",
        captured_at=datetime.now(timezone.utc),
        ocr_text=text,
        summary="Simulated screen capture",
    )
    return ScreenContext(capture=capture, text=text, summary="Simulated screen capture")


def _image_screen_context(tmp_path: Path, *, name: str, color: tuple[int, int, int], text: str = "") -> ScreenContext:
    image_path = tmp_path / f"{name}.png"
    image = Image.new("RGB", (160, 90), color=(245, 245, 245))
    draw = ImageDraw.Draw(image)
    if name == "blue":
        draw.rectangle((0, 0, 160, 42), fill=color)
    else:
        draw.rectangle((0, 0, 76, 90), fill=color)
    image.save(image_path)
    capture = ScreenCaptureRef(
        id=name,
        path=str(image_path),
        width=160,
        height=90,
        mode="simulated",
        captured_at=datetime.now(timezone.utc),
        ocr_text=text,
        summary=f"{name} screen",
    )
    return ScreenContext(capture=capture, text=text, summary=f"{name} screen")


def test_guided_intent_routing():
    assert parse_guided_task_prompt("Guide me through submitting this form")
    assert parse_guided_task_prompt("Show me where to click next")
    assert parse_guided_task_prompt("What time is it?") is None


def test_task_planner_parses_model_json(tmp_path: Path):
    planner = TaskPlanner()
    plan = __import__("asyncio").run(
        planner.plan(
            goal="Guide me through submitting this form",
            screen_context=_screen_context(tmp_path),
            region_context=None,
            evidence=[],
            profile=ProviderConfig(
                id="demo",
                display_name="Demo",
                description="Demo",
                transport="mock",
                backend_base_url="http://127.0.0.1",
                model_name="stub",
                capabilities=ProviderCapabilities(),
            ),
            provider=_StubPlannerProvider(),
            max_steps=5,
        )
    )
    assert plan.title == "Submit the form"
    assert plan.steps[0].target_description == "Submit"


def test_target_grounder_success_and_failure(tmp_path: Path, monkeypatch):
    class _Registry:
        demo_resolver = None
        credential_store = type("Store", (), {"get": lambda self, provider_id: {}})()

    grounder = TargetGrounder(_Registry())
    monkeypatch.setattr(
        grounder,
        "_extract_ocr_boxes",
        lambda _path: [{"text": "Submit", "left": 240, "top": 180, "width": 90, "height": 30}],
    )
    step = GuidedTaskStep(
        step_id="step-1",
        order_index=0,
        instruction_text="Click Submit",
        target_description="Submit button",
        completion_hint="Success",
        grounding_required=True,
    )
    success = __import__("asyncio").run(
        grounder.ground(
            step=step,
            screen_context=_screen_context(tmp_path),
            profile=ProviderConfig(
                id="demo",
                display_name="Demo",
                description="Demo",
                transport="mock",
                backend_base_url="http://127.0.0.1",
                model_name="stub",
                capabilities=ProviderCapabilities(),
            ),
            overlay_style="arrow_pulse",
        )
    )
    assert success.success is True
    assert success.bbox is not None

    monkeypatch.setattr(grounder, "_extract_ocr_boxes", lambda _path: [])
    failed = __import__("asyncio").run(
        grounder.ground(
            step=step,
            screen_context=_screen_context(tmp_path, text="Cancel"),
            profile=ProviderConfig(
                id="demo",
                display_name="Demo",
                description="Demo",
                transport="mock",
                backend_base_url="http://127.0.0.1",
                model_name="stub",
                capabilities=ProviderCapabilities(),
            ),
            overlay_style="arrow_pulse",
        )
    )
    assert failed.success is False
    assert failed.bbox is None


def test_step_progress_detector_conservative_behavior():
    detector = StepProgressDetector()
    step = GuidedTaskStep(
        step_id="step-1",
        order_index=0,
        instruction_text="Click Submit",
        target_description="Submit button",
        completion_hint="Success message",
        grounding_required=True,
    )
    progress = detector.detect(
        step=step,
        grounding=GroundingResult(
            success=True,
            confidence=0.92,
            bbox=OverlayTarget(x=10, y=10, width=80, height=24, target_label="Submit", render_style="arrow_pulse"),
            target_label="Submit",
            reason="Matched",
        ),
        previous_screen_text="Submit Cancel",
        current_screen_text="Success message",
        mode="conservative",
    )
    assert progress.state == "completed"


def test_step_progress_detector_completes_navigation_step_on_screen_change():
    detector = StepProgressDetector()
    step = GuidedTaskStep(
        step_id="step-url",
        order_index=1,
        instruction_text="Type 'kaggle.com' into the address bar and press Enter.",
        target_description="address bar",
        completion_hint="Kaggle page is visible",
        grounding_required=True,
    )
    progress = detector.detect(
        step=step,
        grounding=GroundingResult(
            success=True,
            confidence=0.9,
            bbox=OverlayTarget(x=100, y=20, width=600, height=30, target_label="address bar", render_style="arrow_pulse"),
            target_label="address bar",
            reason="Matched address bar.",
        ),
        previous_screen_text="New Tab Search or type a URL",
        current_screen_text="Kaggle Search Competitions Datasets Models",
        mode="conservative",
        screen_changed=True,
    )
    assert progress.state == "completed"


def test_guided_session_start_advance_stop_flow(tmp_path: Path):
    trace = TraceService(SQLiteTraceLogger(Database(tmp_path / "guided.db")))
    orchestrator = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(type("Registry", (), {"demo_resolver": None, "credential_store": type("Store", (), {"get": lambda self, provider_id: {}})()})()),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace),
    )
    orchestrator.planner.plan = lambda **kwargs: __import__("asyncio").sleep(0, result=GuidedTaskPlan(  # type: ignore[method-assign]
        title="Test task",
        goal="Guide me",
        estimated_steps=2,
        steps=[
            GuidedTaskStep(step_id="1", order_index=0, instruction_text="Click Submit", target_description="Submit", completion_hint="Success", grounding_required=True),
            GuidedTaskStep(step_id="2", order_index=1, instruction_text="Confirm success", target_description="Success", completion_hint="Done", grounding_required=True),
        ],
    ))
    async def _ground_success(**kwargs):
        return GroundingResult(
            success=True,
            confidence=0.9,
            bbox=OverlayTarget(x=100, y=100, width=80, height=24, target_label="Submit", render_style="arrow_pulse"),
            target_label="Submit",
            reason="Matched visible text.",
        )

    orchestrator.grounder.ground = _ground_success  # type: ignore[method-assign]
    started = __import__("asyncio").run(
        orchestrator.start(
            goal="Guide me",
            conversation_id="conv-1",
            screen_context=_screen_context(tmp_path),
            region_context=None,
            evidence=[],
            profile=ProviderConfig(
                id="demo",
                display_name="Demo",
                description="Demo",
                transport="mock",
                backend_base_url="http://127.0.0.1",
                model_name="stub",
                capabilities=ProviderCapabilities(),
            ),
            provider=_StubPlannerProvider(),
            max_steps=4,
            overlay_style="arrow_pulse",
        )
    )
    assert started.ok is True
    assert started.status and started.status.overlay_target is not None
    profile = ProviderConfig(
        id="demo",
        display_name="Demo",
        description="Demo",
        transport="mock",
        backend_base_url="http://127.0.0.1",
        model_name="stub",
        capabilities=ProviderCapabilities(),
    )
    next_status = __import__("asyncio").run(
        orchestrator.confirm_step(
            overlay_style="arrow_pulse",
            screen_context=_screen_context(tmp_path),
            region_context=None,
            profile=profile,
            provider=_StubPlannerProvider(),
        )
    )
    assert next_status.current_step is not None
    stopped = orchestrator.stop()
    assert stopped.ok is True


def test_guided_rescan_reanchors_to_matching_step(tmp_path: Path):
    trace = TraceService(SQLiteTraceLogger(Database(tmp_path / "guided-reanchor.db")))
    orchestrator = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(type("Registry", (), {"demo_resolver": None, "credential_store": type("Store", (), {"get": lambda self, provider_id: {}})()})()),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace),
    )
    orchestrator.planner.plan = lambda **kwargs: __import__("asyncio").sleep(0, result=GuidedTaskPlan(  # type: ignore[method-assign]
        title="Excel chart task",
        goal="Guide me through creating a chart in Excel",
        estimated_steps=3,
        steps=[
            GuidedTaskStep(step_id="1", order_index=0, instruction_text="Open the Insert tab", target_description="Insert", completion_hint="Insert ribbon is visible", grounding_required=True),
            GuidedTaskStep(step_id="2", order_index=1, instruction_text="Choose a chart type", target_description="Charts", completion_hint="Chart menu is open", grounding_required=True),
            GuidedTaskStep(step_id="3", order_index=2, instruction_text="Confirm the chart is inserted", target_description="Chart", completion_hint="Chart appears on sheet", grounding_required=True),
        ],
    ))

    async def _ground_with_reanchor(**kwargs):
        step = kwargs["step"]
        if step.step_id == "1":
            return GroundingResult(
                success=True,
                confidence=0.92,
                bbox=OverlayTarget(x=140, y=84, width=92, height=28, target_label="Insert", render_style="arrow_pulse"),
                target_label="Insert",
                reason="Matched the Insert tab on the current screen.",
            )
        return GroundingResult(
            success=False,
            confidence=0.0,
            bbox=None,
            target_label=None,
            reason=f"Could not locate {step.target_description}.",
            fallback_suggestion="Re-scan.",
        )

    orchestrator.grounder.ground = _ground_with_reanchor  # type: ignore[method-assign]
    profile = ProviderConfig(
        id="demo",
        display_name="Demo",
        description="Demo",
        transport="mock",
        backend_base_url="http://127.0.0.1",
        model_name="stub",
        capabilities=ProviderCapabilities(),
    )
    started = __import__("asyncio").run(
        orchestrator.start(
            goal="Guide me through creating a chart in Excel",
            conversation_id="conv-1",
            screen_context=_screen_context(tmp_path, text="Insert Home Formula"),
            region_context=None,
            evidence=[],
            profile=profile,
            provider=_StubPlannerProvider(),
            max_steps=5,
            overlay_style="arrow_pulse",
        )
    )
    assert started.status is not None
    orchestrator.session_manager.jump_to(2)

    rescanned = __import__("asyncio").run(
        orchestrator.rescan(
            overlay_style="arrow_pulse",
            screen_context=_screen_context(tmp_path, text="Insert Charts Recommended Charts"),
            region_context=None,
            profile=profile,
            provider=_StubPlannerProvider(),
        )
    )
    assert rescanned.current_step is not None
    assert rescanned.current_step.step_id == "1"
    assert rescanned.overlay_target is not None
    assert rescanned.session is not None
    assert rescanned.session.status == "active"


def test_guided_observe_recovers_after_attention_state(tmp_path: Path):
    trace = TraceService(SQLiteTraceLogger(Database(tmp_path / "guided-observe.db")))
    orchestrator = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(type("Registry", (), {"demo_resolver": None, "credential_store": type("Store", (), {"get": lambda self, provider_id: {}})()})()),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace),
    )
    orchestrator.planner.plan = lambda **kwargs: __import__("asyncio").sleep(0, result=GuidedTaskPlan(  # type: ignore[method-assign]
        title="Excel chart task",
        goal="Guide me through creating a chart in Excel",
        estimated_steps=2,
        steps=[
            GuidedTaskStep(step_id="1", order_index=0, instruction_text="Open the Insert tab", target_description="Insert", completion_hint="Insert ribbon is visible", grounding_required=True),
            GuidedTaskStep(step_id="2", order_index=1, instruction_text="Choose a chart type", target_description="Charts", completion_hint="Chart menu is open", grounding_required=True),
        ],
    ))

    async def _ground_recover(**kwargs):
        step = kwargs["step"]
        screen_context = kwargs["screen_context"]
        if "insert" not in screen_context.text.lower():
            return GroundingResult(
                success=False,
                confidence=0.0,
                bbox=None,
                target_label=None,
                reason=f"Could not locate {step.target_description}.",
                fallback_suggestion="Re-scan.",
            )
        return GroundingResult(
            success=True,
            confidence=0.91,
            bbox=OverlayTarget(x=240, y=96, width=92, height=28, target_label="Insert", render_style="arrow_pulse"),
            target_label="Insert",
            reason="Matched the Insert tab on the current screen.",
        )

    orchestrator.grounder.ground = _ground_recover  # type: ignore[method-assign]
    profile = ProviderConfig(
        id="demo",
        display_name="Demo",
        description="Demo",
        transport="mock",
        backend_base_url="http://127.0.0.1",
        model_name="stub",
        capabilities=ProviderCapabilities(),
    )
    started = __import__("asyncio").run(
        orchestrator.start(
            goal="Guide me through creating a chart in Excel",
            conversation_id="conv-1",
            screen_context=_screen_context(tmp_path, text="Home Formulas"),
            region_context=None,
            evidence=[],
            profile=profile,
            provider=_StubPlannerProvider(),
            max_steps=5,
            overlay_style="arrow_pulse",
        )
    )
    assert started.status is not None
    assert started.status.session is not None
    assert started.status.session.status == "needs_attention"

    recovered = __import__("asyncio").run(
        orchestrator.observe(
            screen_context=_screen_context(tmp_path, text="Insert Charts"),
            region_context=None,
            profile=profile,
            provider=_StubPlannerProvider(),
            completion_mode="conservative",
            auto_advance_sensitivity=0.85,
            overlay_style="arrow_pulse",
        )
    )
    assert recovered.session is not None
    assert recovered.session.status == "active"
    assert recovered.overlay_target is not None


def test_guided_rescan_replans_from_current_screen(tmp_path: Path):
    trace = TraceService(SQLiteTraceLogger(Database(tmp_path / "guided-replan.db")))
    orchestrator = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(type("Registry", (), {"demo_resolver": None, "credential_store": type("Store", (), {"get": lambda self, provider_id: {}})()})()),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace),
    )

    call_log: list[str] = []

    async def _planner(**kwargs):
        goal = kwargs["goal"]
        screen_text = kwargs["screen_context"].text
        if "kaggle" in screen_text.lower():
            return GuidedTaskPlan(
                title="Kaggle competitions",
                goal=goal,
                estimated_steps=2,
                steps=[
                    GuidedTaskStep(step_id="k1", order_index=0, instruction_text="Open the Competitions page", target_description="Competitions", completion_hint="Competitions page is open", grounding_required=True),
                    GuidedTaskStep(step_id="k2", order_index=1, instruction_text="Use the prize filter", target_description="Prize", completion_hint="Prize filter is visible", grounding_required=True),
                ],
            )
        return GuidedTaskPlan(
            title="Old plan",
            goal=goal,
            estimated_steps=1,
            steps=[
                GuidedTaskStep(step_id="o1", order_index=0, instruction_text="Click Submit", target_description="Submit", completion_hint="Success", grounding_required=True),
            ],
        )

    async def _ground(**kwargs):
        step = kwargs["step"]
        call_log.append(step.target_description)
        if step.target_description == "Competitions":
            return GroundingResult(
                success=True,
                confidence=0.93,
                bbox=OverlayTarget(x=180, y=120, width=120, height=32, target_label="Competitions", render_style="arrow_pulse"),
                target_label="Competitions",
                reason="Matched the Competitions navigation item.",
            )
        return GroundingResult(
            success=False,
            confidence=0.0,
            bbox=None,
            target_label=None,
            reason=f"Could not locate {step.target_description}.",
            fallback_suggestion="Re-scan.",
        )

    orchestrator.planner.plan = _planner  # type: ignore[method-assign]
    orchestrator.grounder.ground = _ground  # type: ignore[method-assign]
    profile = ProviderConfig(
        id="demo",
        display_name="Demo",
        description="Demo",
        transport="mock",
        backend_base_url="http://127.0.0.1",
        model_name="stub",
        capabilities=ProviderCapabilities(),
    )

    started = __import__("asyncio").run(
        orchestrator.start(
            goal="Guide me to high prize competitions on Kaggle",
            conversation_id="conv-1",
            screen_context=_screen_context(tmp_path, text="Random browser page"),
            region_context=None,
            evidence=[],
            profile=profile,
            provider=_StubPlannerProvider(),
            max_steps=5,
            overlay_style="arrow_pulse",
        )
    )
    assert started.status is not None
    assert started.status.session is not None
    assert started.status.session.status == "needs_attention"

    rescanned = __import__("asyncio").run(
        orchestrator.rescan(
            overlay_style="arrow_pulse",
            screen_context=_screen_context(tmp_path, text="Kaggle Competitions Datasets Models"),
            region_context=None,
            profile=profile,
            provider=_StubPlannerProvider(),
        )
    )
    assert rescanned.session is not None
    assert rescanned.session.status == "active"
    assert rescanned.plan is not None
    assert rescanned.plan.title == "Kaggle competitions"
    assert rescanned.current_step is not None
    assert rescanned.current_step.target_description == "Competitions"
    assert rescanned.overlay_target is not None
    assert "Competitions" in call_log


def test_guided_observe_replans_when_visual_screen_changes_without_ocr(tmp_path: Path):
    trace = TraceService(SQLiteTraceLogger(Database(tmp_path / "guided-visual-change.db")))
    orchestrator = GuidanceOrchestrator(
        session_manager=GuidedTaskSessionManager(),
        planner=TaskPlanner(),
        grounder=TargetGrounder(type("Registry", (), {"demo_resolver": None, "credential_store": type("Store", (), {"get": lambda self, provider_id: {}})()})()),
        progress_detector=StepProgressDetector(),
        recovery_policy=RecoveryPolicy(),
        trace_logger=GuidedTaskTraceLogger(trace),
    )

    async def _planner(**kwargs):
        screen_id = kwargs["screen_context"].capture.id
        if screen_id == "blue":
            return GuidedTaskPlan(
                title="Blue app task",
                goal=kwargs["goal"],
                estimated_steps=1,
                steps=[
                    GuidedTaskStep(step_id="blue-step", order_index=0, instruction_text="Use the visible blue app action", target_description="Blue action", completion_hint="Blue action completed", grounding_required=True),
                ],
            )
        return GuidedTaskPlan(
            title="Red app task",
            goal=kwargs["goal"],
            estimated_steps=1,
            steps=[
                GuidedTaskStep(step_id="red-step", order_index=0, instruction_text="Use the red app action", target_description="Red action", completion_hint="Red action completed", grounding_required=True),
            ],
        )

    async def _ground(**kwargs):
        step = kwargs["step"]
        return GroundingResult(
            success=True,
            confidence=0.91,
            bbox=OverlayTarget(x=20, y=20, width=60, height=28, target_label=step.target_description, render_style="arrow_pulse"),
            target_label=step.target_description,
            reason=f"Grounded {step.target_description}.",
        )

    orchestrator.planner.plan = _planner  # type: ignore[method-assign]
    orchestrator.grounder.ground = _ground  # type: ignore[method-assign]
    profile = ProviderConfig(
        id="demo",
        display_name="Demo",
        description="Demo",
        transport="mock",
        backend_base_url="http://127.0.0.1",
        model_name="stub",
        capabilities=ProviderCapabilities(),
    )

    started = __import__("asyncio").run(
        orchestrator.start(
            goal="Guide me through this task",
            conversation_id="conv-1",
            screen_context=_image_screen_context(tmp_path, name="red", color=(220, 20, 20), text=""),
            region_context=None,
            evidence=[],
            profile=profile,
            provider=_StubPlannerProvider(),
            max_steps=4,
            overlay_style="arrow_pulse",
        )
    )
    assert started.status is not None
    assert started.status.current_step is not None
    assert started.status.current_step.step_id == "red-step"

    observed = __import__("asyncio").run(
        orchestrator.observe(
            screen_context=_image_screen_context(tmp_path, name="blue", color=(20, 20, 220), text=""),
            region_context=None,
            profile=profile,
            provider=_StubPlannerProvider(),
            completion_mode="conservative",
            auto_advance_sensitivity=0.85,
            overlay_style="arrow_pulse",
        )
    )
    assert observed.current_step is not None
    assert observed.current_step.step_id == "blue-step"
    assert observed.overlay_target is not None


def test_answer_service_does_not_hallucinate_guided_target_on_failure(tmp_path: Path, monkeypatch):
    services = build_services(tmp_path)
    guidance = services["guidance"]
    monkeypatch.setattr(
        guidance.planner,
        "plan",
        lambda **kwargs: __import__("asyncio").sleep(0, result=GuidedTaskPlan(
            title="Test task",
            goal="Guide me through this",
            estimated_steps=1,
            steps=[GuidedTaskStep(step_id="1", order_index=0, instruction_text="Click Submit", target_description="Submit", completion_hint="Success", grounding_required=True)],
        )),
    )
    monkeypatch.setattr(
        guidance.grounder,
        "ground",
        lambda **kwargs: __import__("asyncio").sleep(
            0,
            result=GroundingResult(success=False, confidence=0.0, bbox=None, target_label=None, reason="Could not locate Submit.", fallback_suggestion="Re-scan."),
        ),
    )
    response = __import__("asyncio").run(
        services["answer"].answer(ChatRequest(prompt="Guide me through this", use_current_screen=False), screen_context=_screen_context(tmp_path))
    )
    assert response.guided_task_status is not None
    assert response.guided_task_status.overlay_target is None
    assert "could not" in response.answer.lower() or "re-scan" in response.answer.lower()
