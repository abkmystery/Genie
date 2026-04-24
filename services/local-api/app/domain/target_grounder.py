from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

from app.core.text_matching import terms
from app.models.contracts import GroundingResult, GuidedTaskStep, OverlayTarget, ProviderConfig, RegionContext, ScreenContext
from app.providers.demo_credentials import DemoResolverResult
from app.providers.model_payloads import encode_image_data_url
from app.providers.openai_compatible import OpenAICompatibleClient

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None


_JSON_RE = re.compile(r"\{[\s\S]*\}")


class TargetGrounder:
    def __init__(self, provider_registry) -> None:
        self.provider_registry = provider_registry

    async def ground(
        self,
        *,
        step: GuidedTaskStep,
        screen_context: ScreenContext,
        profile: ProviderConfig,
        region_context: RegionContext | None = None,
        overlay_style: str = "arrow_pulse",
    ) -> GroundingResult:
        if not step.grounding_required:
            return GroundingResult(success=True, confidence=1.0, bbox=None, target_label=step.target_description, reason="This step does not require a grounded target.")

        image_path = Path(region_context.capture.path if region_context else screen_context.capture.path)
        heuristic = self._heuristic_target(step=step, screen_context=screen_context, region_context=region_context, overlay_style=overlay_style)
        if heuristic is not None:
            return heuristic

        boxes = self._extract_ocr_boxes(image_path)
        candidates = self._score_candidates(step, boxes)
        if candidates:
            confidence, candidate = candidates[0]
            return self._build_overlay_result(
                candidate=candidate,
                confidence=confidence,
                step=step,
                overlay_style=overlay_style,
                region_context=region_context,
                screen_context=screen_context,
                reason=f"Matched visible text '{str(candidate['text']).strip()}' to the requested target.",
            )

        model_result = await self._ground_with_model(
            step=step,
            screen_context=screen_context,
            region_context=region_context,
            profile=profile,
            overlay_style=overlay_style,
        )
        if model_result is not None:
            return model_result

        return GroundingResult(
            success=False,
            confidence=0.0,
            bbox=None,
            target_label=None,
            reason=f"I could not confidently locate {step.target_description} on the current screen.",
            fallback_suggestion="Try Re-scan, use Draw Region around the relevant area, or follow the text-only instruction.",
        )

    def _build_overlay_result(
        self,
        *,
        candidate: dict[str, object],
        confidence: float,
        step: GuidedTaskStep,
        overlay_style: str,
        region_context: RegionContext | None,
        screen_context: ScreenContext,
        reason: str,
    ) -> GroundingResult:
        offset_x = region_context.selection.x if region_context else 0
        offset_y = region_context.selection.y if region_context else 0
        left = max(0, int(candidate["left"]) - int(candidate.get("pad_x", 10)))
        top = max(0, int(candidate["top"]) - int(candidate.get("pad_y", 7)))
        width = int(candidate["width"]) + (int(candidate.get("pad_x", 10)) * 2)
        height = int(candidate["height"]) + (int(candidate.get("pad_y", 7)) * 2)
        overlay = OverlayTarget(
            x=offset_x + left,
            y=offset_y + top,
            width=max(36, width),
            height=max(30, height),
            capture_width=screen_context.capture.width,
            capture_height=screen_context.capture.height,
            target_label=str(candidate["text"]).strip(),
            annotation=step.instruction_text,
            render_style=overlay_style if overlay_style in {"arrow_only", "highlight_only", "arrow_pulse"} else "arrow_pulse",
        )
        return GroundingResult(
            success=True,
            confidence=confidence,
            bbox=overlay,
            target_label=overlay.target_label,
            reason=reason,
            fallback_suggestion=None,
        )

    def _extract_ocr_boxes(self, image_path: Path) -> list[dict[str, object]]:
        if pytesseract is None:
            return []
        try:
            data = pytesseract.image_to_data(Image.open(image_path), output_type=pytesseract.Output.DICT)
        except Exception:
            return []

        results: list[dict[str, object]] = []
        for index, raw_text in enumerate(data.get("text", [])):
            text = str(raw_text or "").strip()
            if not text:
                continue
            width = int(data["width"][index])
            height = int(data["height"][index])
            if width <= 0 or height <= 0:
                continue
            results.append(
                {
                    "text": text,
                    "left": int(data["left"][index]),
                    "top": int(data["top"][index]),
                    "width": width,
                    "height": height,
                }
            )
        return results

    def _score_candidates(self, step: GuidedTaskStep, boxes: list[dict[str, object]]) -> list[tuple[float, dict[str, object]]]:
        desired_terms = terms(f"{step.target_description} {step.instruction_text}")
        if not desired_terms:
            return []
        scored: list[tuple[float, dict[str, object]]] = []
        for candidate in boxes:
            candidate_terms = terms(str(candidate["text"]))
            if not candidate_terms:
                continue
            overlap = desired_terms & candidate_terms
            if not overlap:
                continue
            confidence = min(0.98, 0.45 + (len(overlap) / max(1, len(desired_terms))) * 0.5)
            scored.append((confidence, candidate))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _heuristic_target(
        self,
        *,
        step: GuidedTaskStep,
        screen_context: ScreenContext,
        region_context: RegionContext | None,
        overlay_style: str,
    ) -> GroundingResult | None:
        text = f"{step.instruction_text} {step.target_description}".lower()
        screen_text = f"{screen_context.summary} {screen_context.text}".lower()
        if (
            any(marker in text for marker in ("filter", "sort", "prize", "reward", "highest"))
            and any(marker in screen_text for marker in ("kaggle", "competition", "competitions"))
        ):
            capture = region_context.capture if region_context else screen_context.capture
            candidate = {
                "text": "competition filters and sorting",
                "left": int(capture.width * 0.04),
                "top": int(capture.height * 0.13),
                "width": int(capture.width * 0.92),
                "height": max(96, int(capture.height * 0.2)),
                "pad_x": 0,
                "pad_y": 0,
            }
            return self._build_overlay_result(
                candidate=candidate,
                confidence=0.72,
                step=step,
                overlay_style="highlight_only" if overlay_style == "arrow_pulse" else overlay_style,
                region_context=region_context,
                screen_context=screen_context,
                reason="Highlighted the visible Kaggle filter and sorting area for this broad filter step.",
            )

        if not any(marker in text for marker in ("address bar", "url bar", "browser address", "type url", "enter a url")):
            return None

        capture = region_context.capture if region_context else screen_context.capture
        candidate = {
            "text": "address bar",
            "left": int(capture.width * 0.065),
            "top": int(capture.height * 0.052),
            "width": int(capture.width * 0.76),
            "height": max(34, int(capture.height * 0.032)),
            "pad_x": 0,
            "pad_y": 0,
        }
        return self._build_overlay_result(
            candidate=candidate,
            confidence=0.82,
            step=step,
            overlay_style=overlay_style,
            region_context=region_context,
            screen_context=screen_context,
            reason="Estimated the browser address bar from the visible browser chrome.",
        )

    async def _ground_with_model(
        self,
        *,
        step: GuidedTaskStep,
        screen_context: ScreenContext,
        region_context: RegionContext | None,
        profile: ProviderConfig,
        overlay_style: str,
    ) -> GroundingResult | None:
        resolved = await self._resolve_openai_compatible_target(profile)
        if resolved is None:
            return None

        image_context = region_context.capture if region_context else screen_context.capture
        image = encode_image_data_url(image_context.path)
        if image is None:
            return None

        payload = {
            "model": resolved["model"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You locate on-screen UI targets from screenshots. "
                        "Return JSON only with this exact schema: "
                        '{"found":true,"confidence":0.0,"x":0,"y":0,"width":0,"height":0,"label":"","reason":""}. '
                        "Coordinates must be normalized integers from 0 to 1000 relative to the provided image. "
                        "If you are not confident, return found=false and confidence below 0.6. "
                        "Ignore Genie companion UI, launcher buttons, chat controls, and overlays. Focus on the underlying app or website."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Find the UI target for this step.\n"
                                f"Instruction: {step.instruction_text}\n"
                                f"Target description: {step.target_description}\n"
                                f"Completion hint: {step.completion_hint}\n"
                                f"Screen summary: {(region_context.summary if region_context else screen_context.summary)}"
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image}},
                    ],
                },
            ],
            "temperature": 0.0,
        }

        try:
            client = OpenAICompatibleClient(
                base_url=resolved["base_url"],
                bearer_token=resolved["token"],
                timeout_s=resolved["timeout_s"],
            )
            raw = await client.chat_completions(payload)
        except Exception:
            return None

        parsed = self._parse_model_grounding(raw)
        if not parsed or not parsed.get("found"):
            return None

        confidence = float(parsed.get("confidence") or 0.0)
        if confidence < 0.55:
            return None

        width = max(1, int(round((float(parsed.get("width") or 0) / 1000) * image_context.width)))
        height = max(1, int(round((float(parsed.get("height") or 0) / 1000) * image_context.height)))
        left = int(round((float(parsed.get("x") or 0) / 1000) * image_context.width))
        top = int(round((float(parsed.get("y") or 0) / 1000) * image_context.height))

        refined = self._refine_with_ocr(
            left=left,
            top=top,
            width=width,
            height=height,
            step=step,
            model_label=str(parsed.get("label") or ""),
            boxes=self._extract_ocr_boxes(Path(image_context.path)),
        )
        if refined is not None:
            left, top, width, height, label = refined
        else:
            label = str(parsed.get("label") or step.target_description)

        return self._build_overlay_result(
            candidate={
                "text": label,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            },
            confidence=min(0.98, confidence),
            step=step,
            overlay_style=overlay_style,
            region_context=region_context,
            screen_context=screen_context,
            reason=str(parsed.get("reason") or f"Model located {parsed.get('label') or step.target_description} on screen."),
        )

    async def _resolve_openai_compatible_target(self, profile: ProviderConfig) -> dict[str, object] | None:
        if profile.id == "demo" and self.provider_registry.demo_resolver is not None:
            resolved: DemoResolverResult = await self.provider_registry.demo_resolver.resolve(
                demo_source_order=profile.demo_source_order,
                remote_demo_file_url=profile.remote_demo_file_url,
                remote_demo_file_format=profile.remote_demo_file_format,
                default_base_url=(profile.backend_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"),
                default_model=(profile.default_model or profile.model_name or "gemma-4-26b-a4b-it"),
                default_timeout_ms=profile.timeout_ms or 60000,
            )
            if not resolved.api_key:
                return None
            return {
                "base_url": resolved.status.base_url.rstrip("/"),
                "token": resolved.api_key,
                "model": resolved.status.model,
                "timeout_s": max(5, resolved.status.timeout_ms / 1000),
            }

        if profile.transport == "http" and (profile.api_style or "genie_gateway") == "openai_compatible":
            credentials = self.provider_registry.credential_store.get(profile.id) or {}
            return {
                "base_url": (profile.endpoint_override or profile.backend_base_url or "").rstrip("/"),
                "token": credentials.get("token") or "",
                "model": profile.model_name,
                "timeout_s": max(5, profile.timeout_ms / 1000),
            }

        return None

    def _parse_model_grounding(self, raw: str) -> dict[str, object] | None:
        match = _JSON_RE.search(raw)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _refine_with_ocr(
        self,
        *,
        left: int,
        top: int,
        width: int,
        height: int,
        step: GuidedTaskStep,
        model_label: str,
        boxes: list[dict[str, object]],
    ) -> tuple[int, int, int, int, str] | None:
        if not boxes:
            return None
        desired_terms = terms(f"{step.target_description} {step.instruction_text} {model_label}")
        center_x = left + (width / 2)
        center_y = top + (height / 2)
        search_left = left - max(40, width // 2)
        search_top = top - max(32, height // 2)
        search_right = left + width + max(40, width // 2)
        search_bottom = top + height + max(32, height // 2)

        nearest: tuple[float, dict[str, object]] | None = None
        for candidate in boxes:
            candidate_terms = terms(str(candidate["text"]))
            if desired_terms and not (candidate_terms & desired_terms):
                continue
            candidate_left = int(candidate["left"])
            candidate_top = int(candidate["top"])
            candidate_width = int(candidate["width"])
            candidate_height = int(candidate["height"])
            candidate_center_x = candidate_left + (candidate_width / 2)
            candidate_center_y = candidate_top + (candidate_height / 2)
            if not (search_left <= candidate_center_x <= search_right and search_top <= candidate_center_y <= search_bottom):
                continue
            distance = ((candidate_center_x - center_x) ** 2 + (candidate_center_y - center_y) ** 2) ** 0.5
            if nearest is None or distance < nearest[0]:
                nearest = (distance, candidate)

        if nearest is None:
            return None
        chosen = nearest[1]
        return (
            int(chosen["left"]),
            int(chosen["top"]),
            max(24, int(chosen["width"])),
            max(24, int(chosen["height"])),
            str(chosen["text"]).strip(),
        )
