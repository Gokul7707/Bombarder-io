"""Military-style performance grading and AAR generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PerformanceReport:
    overall_score: float
    passed: bool
    categories: Dict[str, float]
    violations: List[str]
    recommendations: List[str]
    grade: str


class PerformanceEvaluator:
    GRADES = [(90, "DISTINCTION"), (80, "PASS"), (70, "MARGINAL"), (0, "FAIL")]

    def __init__(self, weights: Dict[str, float], pass_threshold: int = 70) -> None:
        self.weights = weights
        self.pass_threshold = pass_threshold
        self.cuts_correct = 0
        self.cuts_total = 0
        self.steadiness_samples: List[float] = []
        self.tremor_samples: List[float] = []
        self.phases_completed = 0
        self.phases_required = 0
        self.violations: List[str] = []
        self.remote_tool_placed = False
        self.report_submitted = False

    def reset(self, phases_required: int) -> None:
        self.cuts_correct = 0
        self.cuts_total = 0
        self.steadiness_samples.clear()
        self.tremor_samples.clear()
        self.phases_completed = 0
        self.phases_required = phases_required
        self.violations.clear()
        self.remote_tool_placed = False
        self.report_submitted = False

    def sample_biometrics(self, stability: float, tremor: float) -> None:
        self.steadiness_samples.append(stability)
        self.tremor_samples.append(tremor)

    def record_cut(self, correct: bool) -> None:
        self.cuts_total += 1
        if correct:
            self.cuts_correct += 1

    def record_phase(self) -> None:
        self.phases_completed += 1

    def add_violation(self, msg: str) -> None:
        self.violations.append(msg)

    def evaluate(self, mission_pass_score: int, mission_success: bool) -> PerformanceReport:
        protocol = min(1.0, self.phases_completed / max(1, self.phases_required))
        if self.remote_tool_placed or self.phases_required <= 3:
            protocol = min(1.0, protocol + 0.1)

        steadiness = (
            sum(self.steadiness_samples) / len(self.steadiness_samples)
            if self.steadiness_samples
            else 0.0
        )
        avg_tremor = (
            sum(self.tremor_samples) / len(self.tremor_samples)
            if self.tremor_samples
            else 0.0
        )
        hand_score = max(0.0, steadiness * 0.6 + (1 - avg_tremor) * 0.4)

        precision = (
            self.cuts_correct / self.cuts_total if self.cuts_total else (1.0 if mission_success else 0.0)
        )

        decision = 1.0 if mission_success else max(0.0, precision - len(self.violations) * 0.15)
        reporting = 1.0 if self.report_submitted else 0.5

        categories = {
            "protocol_compliance": round(protocol * 100, 1),
            "teleop_readiness": round(hand_score * 100, 1),
            "rsp_precision": round(precision * 100, 1),
            "decision_quality": round(decision * 100, 1),
            "aar_reporting": round(reporting * 100, 1),
        }

        overall = sum(categories[k] * self.weights.get(k, 0.2) for k in categories)
        passed = overall >= mission_pass_score and mission_success

        grade = "FAIL"
        for threshold, label in self.GRADES:
            if overall >= threshold:
                grade = label
                break

        recommendations = []
        if categories["teleop_readiness"] < 70:
            recommendations.append("Practice remote teleop stabilization before live RSP")
        if categories["protocol_compliance"] < 80:
            recommendations.append("Review 5 Cs checklist — complete all phases in order")
        if self.violations:
            recommendations.append(f"Address {len(self.violations)} protocol violation(s) in AAR")

        return PerformanceReport(
            overall_score=round(overall, 1),
            passed=passed,
            categories=categories,
            violations=list(self.violations),
            recommendations=recommendations,
            grade=grade,
        )
