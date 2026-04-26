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
        candidates = self._score_candidates(step, self._candidate_pool(boxes))
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
            target_bbox_source=str(candidate.get("bbox_source") or ("ocr" if candidate.get("source") else "heuristic")),
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

    def _candidate_pool(self, boxes: list[dict[str, object]]) -> list[dict[str, object]]:
        """Return individual OCR words plus merged line/phrase candidates.

        Tesseract often splits a visible target like "Search competitions" or
        "Create your own" into separate words. Matching only word boxes makes
        guidance feel jumpy and inaccurate. Merged candidates keep coordinates
        tied to what the user actually sees.
        """

        if not boxes:
            return []

        candidates = [dict(item, source="word") for item in boxes]
        lines: list[list[dict[str, object]]] = []
        for box in sorted(boxes, key=lambda item: (int(item["top"]), int(item["left"]))):
            center_y = int(box["top"]) + (int(box["height"]) / 2)
            placed = False
            for line in lines:
                line_center = sum(int(item["top"]) + (int(item["height"]) / 2) for item in line) / len(line)
                median_height = max(10, sum(int(item["height"]) for item in line) / len(line))
                if abs(center_y - line_center) <= max(8, median_height * 0.65):
                    line.append(box)
                    placed = True
                    break
            if not placed:
                lines.append([box])

        for line in lines:
            ordered = sorted(line, key=lambda item: int(item["left"]))
            segments: list[list[dict[str, object]]] = []
            current: list[dict[str, object]] = []
            previous_right: int | None = None
            for item in ordered:
                left = int(item["left"])
                if previous_right is not None and left - previous_right > 140 and current:
                    segments.append(current)
                    current = []
                current.append(item)
                previous_right = int(item["left"]) + int(item["width"])
            if current:
                segments.append(current)

            for segment in segments:
                if len(segment) < 2:
                    continue
                candidates.append(self._merge_boxes(segment, source="line"))
                # Sliding phrases catch labels embedded inside a longer row.
                for size in range(2, min(5, len(segment)) + 1):
                    for start in range(0, len(segment) - size + 1):
                        candidates.append(self._merge_boxes(segment[start : start + size], source="phrase"))
        return candidates

    def _merge_boxes(self, boxes: list[dict[str, object]], *, source: str) -> dict[str, object]:
        left = min(int(item["left"]) for item in boxes)
        top = min(int(item["top"]) for item in boxes)
        right = max(int(item["left"]) + int(item["width"]) for item in boxes)
        bottom = max(int(item["top"]) + int(item["height"]) for item in boxes)
        return {
            "text": " ".join(str(item["text"]).strip() for item in boxes if str(item["text"]).strip()),
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
            "source": source,
        }

    def _score_candidates(self, step: GuidedTaskStep, boxes: list[dict[str, object]]) -> list[tuple[float, dict[str, object]]]:
        desired_terms = terms(f"{step.target_description} {step.instruction_text}")
        if not desired_terms:
            return []
        desired_text = f"{step.target_description} {step.instruction_text}".lower()
        wants_control = self._looks_like_control_request(desired_text)
        wants_address_bar = any(marker in desired_text for marker in ("address bar", "url bar", "type a url", "enter a url"))
        wants_new_tab = "new tab" in desired_text
        scored: list[tuple[float, dict[str, object]]] = []
        for candidate in boxes:
            candidate_terms = terms(str(candidate["text"]))
            candidate_text = str(candidate["text"]).strip().lower()
            if wants_new_tab and candidate_text in {"+", "＋"}:
                decorated = dict(candidate, bbox_source="ocr")
                scored.append((0.99, decorated))
                continue
            if not candidate_terms:
                continue
            overlap = desired_terms & candidate_terms
            address_match = wants_address_bar and {"search", "url", "type"} & candidate_terms
            if not overlap and not address_match:
                continue
            effective_overlap_count = len(overlap) + (2 if address_match else 0)
            coverage = effective_overlap_count / max(1, len(desired_terms))
            precision = len(overlap) / max(1, len(candidate_terms))
            exact_bonus = 0.16 if self._contains_phrase(str(candidate["text"]), desired_text) else 0.0
            address_bonus = 0.18 if address_match else 0.0
            control_bonus = 0.12 if wants_control and self._looks_like_interactive_label(str(candidate["text"])) else 0.0
            line_bonus = 0.08 if candidate.get("source") in {"line", "phrase"} and len(candidate_terms) > 1 else 0.0
            size_penalty = 0.12 if int(candidate["width"]) > 900 and precision < 0.75 else 0.0
            confidence = min(0.98, 0.38 + (coverage * 0.34) + (precision * 0.18) + exact_bonus + address_bonus + control_bonus + line_bonus - size_penalty)
            decorated = self._decorate_candidate(candidate, desired_text)
            scored.append((confidence, decorated))
        scored.sort(key=lambda item: (item[0], -int(item[1]["width"])), reverse=True)
        return scored

    def _decorate_candidate(self, candidate: dict[str, object], desired_text: str) -> dict[str, object]:
        decorated = dict(candidate)
        if "search" in desired_text or "input" in desired_text or "field" in desired_text:
            decorated["pad_x"] = max(18, int(int(candidate["width"]) * 0.25))
            decorated["pad_y"] = max(10, int(int(candidate["height"]) * 0.45))
        elif self._looks_like_control_request(desired_text) or self._looks_like_interactive_label(str(candidate["text"])):
            decorated["pad_x"] = max(14, int(int(candidate["width"]) * 0.18))
            decorated["pad_y"] = max(8, int(int(candidate["height"]) * 0.35))
        return decorated

    def _contains_phrase(self, candidate_text: str, desired_text: str) -> bool:
        candidate = " ".join(candidate_text.lower().split())
        for phrase in re.findall(r"[a-z0-9][a-z0-9 ]{2,}", desired_text):
            phrase = " ".join(phrase.split())
            if len(phrase.split()) >= 2 and phrase in candidate:
                return True
        return False

    def _looks_like_control_request(self, text: str) -> bool:
        return any(
            word in text
            for word in (
                "click",
                "select",
                "open",
                "choose",
                "press",
                "tap",
                "filter",
                "search",
                "tab",
                "button",
                "field",
                "menu",
                "dropdown",
            )
        )

    def _looks_like_interactive_label(self, text: str) -> bool:
        label_terms = terms(text)
        common_controls = {
            "add",
            "apply",
            "back",
            "cancel",
            "continue",
            "create",
            "done",
            "edit",
            "filter",
            "filters",
            "next",
            "open",
            "save",
            "search",
            "select",
            "submit",
            "tab",
            "view",
        }
        return bool(label_terms & common_controls) or len(label_terms) <= 3

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
        capture = region_context.capture if region_context else screen_context.capture
        is_kaggle_competitions = any(marker in screen_text for marker in ("kaggle", "competition", "competitions"))

        if is_kaggle_competitions and "filter" in text:
            # Kaggle's competition page places a compact Filters control at the
            # far right of the competition search bar. Ground that specific
            # button instead of highlighting the entire filter/category region.
            candidate = {
                "text": "Filters",
                "left": int(capture.width * 0.825),
                "top": int(capture.height * 0.425),
                "width": max(86, int(capture.width * 0.055)),
                "height": max(36, int(capture.height * 0.045)),
                "pad_x": 12,
                "pad_y": 8,
                "bbox_source": "heuristic",
            }
            return self._build_overlay_result(
                candidate=candidate,
                confidence=0.86,
                step=step,
                overlay_style=overlay_style,
                region_context=region_context,
                screen_context=screen_context,
                reason="Located Kaggle's Filters button at the right side of the competition search bar.",
            )

        if is_kaggle_competitions and any(marker in text for marker in ("competitions tab", "competitions page", "open competitions", "click competitions")):
            candidate = {
                "text": "Competitions",
                "left": int(capture.width * 0.01),
                "top": int(capture.height * 0.225),
                "width": max(170, int(capture.width * 0.105)),
                "height": max(40, int(capture.height * 0.055)),
                "pad_x": 8,
                "pad_y": 4,
                "bbox_source": "heuristic",
            }
            return self._build_overlay_result(
                candidate=candidate,
                confidence=0.84,
                step=step,
                overlay_style=overlay_style,
                region_context=region_context,
                screen_context=screen_context,
                reason="Located the Kaggle Competitions navigation item in the left sidebar.",
            )

        if (
            any(marker in text for marker in ("filter", "sort", "prize", "reward", "highest"))
            and is_kaggle_competitions
        ):
            candidate = {
                "text": "competition filters and sorting",
                "left": int(capture.width * 0.25),
                "top": int(capture.height * 0.425),
                "width": int(capture.width * 0.62),
                "height": max(100, int(capture.height * 0.2)),
                "pad_x": 0,
                "pad_y": 0,
                "bbox_source": "heuristic",
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

        candidate = {
            "text": "address bar",
            "left": int(capture.width * 0.065),
            "top": int(capture.height * 0.052),
            "width": int(capture.width * 0.76),
            "height": max(34, int(capture.height * 0.032)),
            "pad_x": 0,
            "pad_y": 0,
            "bbox_source": "heuristic",
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
                "bbox_source": "model",
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
