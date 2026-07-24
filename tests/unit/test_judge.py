"""Tests for the LLM-judge scorer with a fake client."""

from __future__ import annotations

from reforge.llm.client import AssistantTurn, LLMUsage, ToolCall
from reforge.scoring.base import TaskScoringContext
from reforge.scoring.judge import JudgeScorer
from reforge.spec.models import Rubric, RubricCriterion, Source, TaskSpec, Verification
from tests.unit.fakes import FakeContainer


class FakeJudgeClient:
    def __init__(self, scores: dict) -> None:
        self.model = "claude-sonnet-4-6"
        self._scores = scores

    def chat(self, **kwargs) -> AssistantTurn:
        return AssistantTurn(
            text=None,
            tool_calls=[ToolCall(id="1", name="submit_evaluation", arguments=self._scores)],
            usage=LLMUsage(200, 50),
        )


def _spec_with_rubric() -> TaskSpec:
    return TaskSpec(
        id="j",
        category="new_feature",
        title="t",
        instruction="add a feature",
        source=Source(type="local", path="src"),
        verification=Verification(entrypoint="verifier/run_tests.sh", fail_to_pass=["a::b"]),
        rubric=Rubric(
            criteria=[
                RubricCriterion(id="correctness", weight=0.75, prompt="correct?", scale=(0, 5)),
                RubricCriterion(id="style", weight=0.25, prompt="idiomatic?", scale=(0, 5)),
            ]
        ),
    )


def test_judge_weights_and_normalizes() -> None:
    client = FakeJudgeClient(
        {
            "correctness": {"score": 5, "reason": "perfect"},
            "style": {"score": 1, "reason": "meh"},
        }
    )
    ctx = TaskScoringContext(
        spec=_spec_with_rubric(), container=FakeContainer(), diff="+ code", workspace_path="/w"
    )
    result = JudgeScorer(client).score(ctx)
    # correctness 5/5=1.0 * 0.75 + style 1/5=0.2 * 0.25 = 0.8
    assert result.score == 0.8
    assert result.passed is True  # judge never gates
    assert result.detail["criteria"]["correctness"]["normalized"] == 1.0
    assert result.detail["judge_model"] == "claude-sonnet-4-6"


def test_judge_empty_rubric_is_full_score() -> None:
    spec = _spec_with_rubric().model_copy(update={"rubric": Rubric(criteria=[])})
    ctx = TaskScoringContext(spec=spec, container=FakeContainer(), diff="", workspace_path="/w")
    result = JudgeScorer(FakeJudgeClient({})).score(ctx)
    assert result.score == 1.0
