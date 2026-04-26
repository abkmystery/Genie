from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "local-api"))

from app.domain.target_grounder import TargetGrounder  # noqa: E402
from app.models.contracts import GuidedTaskStep  # noqa: E402


@dataclass(frozen=True)
class GoldenCase:
    name: str
    instruction: str
    target: str
    boxes: list[dict[str, object]]
    expected_label: str
    max_center_distance: float = 90.0


def box(text: str, left: int, top: int, width: int, height: int) -> dict[str, object]:
    return {"text": text, "left": left, "top": top, "width": width, "height": height}


def center(candidate: dict[str, object]) -> tuple[float, float]:
    return (float(candidate["left"]) + float(candidate["width"]) / 2, float(candidate["top"]) + float(candidate["height"]) / 2)


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def make_cases() -> list[GoldenCase]:
    common_noise = [
        box("Home", 64, 138, 50, 24),
        box("Search", 540, 18, 80, 24),
        box("Create", 62, 82, 70, 24),
        box("Your Work", 64, 420, 110, 24),
    ]
    return [
        GoldenCase("kaggle filters", "Click Filters to filter competitions by prize", "Filters button", common_noise + [box("Filters", 1610, 326, 74, 28)], "Filters"),
        GoldenCase("kaggle competitions nav", "Open the Competitions page", "Competitions navigation item", common_noise + [box("Competitions", 64, 182, 118, 24)], "Competitions"),
        GoldenCase("kaggle search competitions", "Click Search competitions", "Search competitions input", common_noise + [box("Search competitions", 536, 334, 178, 26)], "Search competitions"),
        GoldenCase("kaggle hackathons", "Choose Hackathons category", "Hackathons card", common_noise + [box("Hackathons", 888, 402, 110, 24)], "Hackathons"),
        GoldenCase("kaggle research", "Choose Research category", "Research card", common_noise + [box("Research", 1280, 402, 86, 24)], "Research"),
        GoldenCase("browser address bar", "Click the browser address bar", "address bar", [box("Search Secure Search or type a URL", 154, 62, 300, 22)], "Search Secure Search or type a URL"),
        GoldenCase("browser new tab", "Open a new tab", "new tab button", [box("+", 265, 20, 16, 16), box("New Tab", 48, 20, 80, 20)], "+"),
        GoldenCase("excel insert tab", "Click Insert in Excel", "Insert tab", [box("Home", 86, 90, 48, 20), box("Insert", 146, 90, 54, 20)], "Insert"),
        GoldenCase("excel recommended charts", "Click Recommended Charts", "Recommended Charts button", [box("Recommended Charts", 412, 128, 170, 24)], "Recommended Charts"),
        GoldenCase("generic submit", "Click Submit", "Submit button", [box("Cancel", 900, 650, 72, 30), box("Submit", 990, 650, 80, 30)], "Submit"),
        GoldenCase("generic continue", "Press Continue", "Continue button", [box("Back", 820, 650, 60, 30), box("Continue", 900, 650, 100, 30)], "Continue"),
        GoldenCase("generic save", "Click Save changes", "Save changes button", [box("Discard", 850, 650, 80, 30), box("Save changes", 946, 650, 128, 30)], "Save changes"),
        GoldenCase("portal sign in", "Click Sign in", "Sign in button", [box("Email", 680, 310, 70, 24), box("Sign in", 680, 440, 82, 32)], "Sign in"),
        GoldenCase("portal password", "Click Password field", "Password field", [box("Email", 680, 310, 70, 24), box("Password", 680, 380, 104, 24)], "Password"),
        GoldenCase("settings diagnostics", "Run Diagnostics", "Run Diagnostics button", [box("Open Logs Folder", 1060, 82, 150, 28), box("Run Diagnostics", 1060, 355, 148, 28)], "Run Diagnostics"),
        GoldenCase("genie sources tab", "Click Sources", "Sources tab", [box("Chat", 34, 124, 42, 24), box("Sources", 106, 124, 76, 24)], "Sources"),
        GoldenCase("form state dropdown", "Open State dropdown", "State dropdown", [box("City", 520, 420, 42, 22), box("State", 520, 488, 54, 22)], "State"),
        GoldenCase("shopping cart checkout", "Click Checkout", "Checkout button", [box("Continue shopping", 880, 620, 165, 28), box("Checkout", 1070, 620, 105, 28)], "Checkout"),
        GoldenCase("modal close", "Close the dialog", "Close button", [box("Cancel", 910, 520, 76, 30), box("Close", 1002, 520, 72, 30)], "Close"),
        GoldenCase("docs upload", "Click Upload file", "Upload file button", [box("New folder", 720, 140, 108, 28), box("Upload file", 850, 140, 114, 28)], "Upload file"),
    ]


def run_eval() -> dict[str, object]:
    grounder = TargetGrounder(provider_registry=None)
    results = []
    for index, case in enumerate(make_cases(), start=1):
        step = GuidedTaskStep(
            step_id=f"golden-{index}",
            order_index=0,
            instruction_text=case.instruction,
            target_description=case.target,
            completion_hint="",
            grounding_required=True,
        )
        candidates = grounder._score_candidates(step, grounder._candidate_pool(case.boxes))
        if not candidates:
            results.append({"name": case.name, "passed": False, "reason": "no candidate"})
            continue
        confidence, candidate = candidates[0]
        expected = next(item for item in case.boxes if str(item["text"]) == case.expected_label)
        center_distance = distance(center(candidate), center(expected))
        passed = center_distance <= case.max_center_distance and confidence >= 0.55
        results.append(
            {
                "name": case.name,
                "passed": passed,
                "confidence": round(confidence, 3),
                "chosen": candidate["text"],
                "expected": case.expected_label,
                "center_distance": round(center_distance, 2),
            }
        )
    passed_count = sum(1 for item in results if item["passed"])
    return {"passed": passed_count, "total": len(results), "results": results}


def main() -> int:
    report = run_eval()
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "guidance-eval.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Guidance Eval Report",
        "",
        f"Passed {report['passed']} of {report['total']} synthetic grounding cases.",
        "",
        "| Case | Result | Chosen | Distance |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["results"]:
        lines.append(
            f"| {item['name']} | {'PASS' if item['passed'] else 'FAIL'} | {item.get('chosen', '-')} | {item.get('center_distance', '-')} |"
        )
    (reports_dir / "guidance-eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Guidance eval: {report['passed']}/{report['total']} passed")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
