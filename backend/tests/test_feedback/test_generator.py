import asyncio
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.services.adaptive import AssistanceLevel
from app.services.evaluation.schemas import (
    EvaluationResult,
    TestCaseResult as EvaluationTestCaseResult,
)
from app.services.feedback import OllamaFeedbackGenerator, build_feedback_prompt


def _evaluation(
    *,
    status: str = "WRONG_ANSWER",
    score: str | None = "50.00",
    compilation_error: str | None = None,
    runtime_error: str | None = None,
    test_case_results: list[EvaluationTestCaseResult] | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        status=status,  # type: ignore[arg-type]
        passed_tests=1,
        total_tests=2,
        score=Decimal(score) if score is not None else None,
        execution_time_ms=12,
        compilation_error=compilation_error,
        runtime_error=runtime_error,
        test_case_results=test_case_results or [],
    )


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    ("level", "expected_guidance"),
    [
        (AssistanceLevel.HIGH, "step-by-step debugging guidance"),
        (AssistanceLevel.MODERATE, "targeted hints"),
        (AssistanceLevel.LOW, "one small conceptual hint"),
    ],
)
def test_prompt_varies_by_assistance_level(
    level: AssistanceLevel,
    expected_guidance: str,
) -> None:
    prompt = build_feedback_prompt("Add two numbers.", "class Main {}", _evaluation(), level)

    assert f"Assistance level: {level.value}" in prompt
    assert expected_guidance in prompt
    if level is not AssistanceLevel.HIGH:
        assert "Do not provide the complete solution." in prompt or (
            "Never reveal or write the complete solution." in prompt
        )


def test_prompt_contains_only_safe_aggregate_evaluation_information() -> None:
    evaluation = _evaluation(
        runtime_error="hidden input echoed by student's program",
        test_case_results=[
            EvaluationTestCaseResult(
                test_case_id=987,
                status="WRONG_ANSWER",
                actual_output="hidden actual output",
                error_message="hidden case diagnostic",
            )
        ],
    )

    prompt = build_feedback_prompt(
        "Problem description",
        "public class Main {}",
        evaluation,
        AssistanceLevel.HIGH,
    )

    assert '"status": "WRONG_ANSWER"' in prompt
    assert '"score": "50.00"' in prompt
    assert '"passed_tests": 1' in prompt
    assert '"compilation_error": null' in prompt
    assert '"expected_output"' not in prompt
    assert '"failed_test_cases"' not in prompt
    assert '"execution_time_ms"' not in prompt
    assert "hidden input echoed" not in prompt
    assert "hidden actual output" not in prompt
    assert "hidden case diagnostic" not in prompt
    assert "987" not in prompt
    assert "Never invent compiler messages, failed test cases, expected outputs" in prompt
    assert "label code-based explanations as hypotheses" in prompt


def test_prompt_includes_verified_compilation_error_but_not_unrelated_runtime_text() -> None:
    prompt = build_feedback_prompt(
        "Problem",
        "class Main {}",
        _evaluation(
            status="COMPILATION_ERROR",
            score=None,
            compilation_error="';' expected at line 3",
            runtime_error="should not be included",
        ),
        AssistanceLevel.HIGH,
    )

    assert "';' expected at line 3" in prompt
    assert "should not be included" not in prompt


def test_sends_expected_ollama_request_and_parses_success() -> None:
    captured: dict[str, Any] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "  Check your loop bounds.  "})

    service = OllamaFeedbackGenerator(
        config=_settings(OLLAMA_BASE_URL="http://ollama.test/", OLLAMA_MODEL="local-model"),
        transport=httpx.MockTransport(respond),
    )

    result = asyncio.run(
        service.generate_feedback(
            "Add two values.",
            "class Main {}",
            _evaluation(),
            AssistanceLevel.MODERATE,
        )
    )

    assert captured["url"] == "http://ollama.test/api/generate"
    assert captured["payload"]["model"] == "local-model"
    assert captured["payload"]["stream"] is False
    assert "Assistance level: MODERATE" in captured["payload"]["prompt"]
    assert result.feedback_text == "Check your loop bounds."
    assert result.model_name == "local-model"
    assert result.generation_status == "SUCCEEDED"
    assert result.error_message is None


def test_empty_model_response_returns_failed_result() -> None:
    service = OllamaFeedbackGenerator(
        config=_settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"response": "  "})
        ),
    )

    result = asyncio.run(
        service.generate_feedback("Problem", "code", _evaluation(), "LOW")
    )

    assert result.generation_status == "FAILED"
    assert result.feedback_text is None
    assert result.error_message == "Ollama returned an empty response."


def test_connection_failure_returns_failed_result() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable", request=request)

    service = OllamaFeedbackGenerator(
        config=_settings(),
        transport=httpx.MockTransport(fail),
    )

    result = asyncio.run(
        service.generate_feedback("Problem", "code", _evaluation(), "LOW")
    )

    assert result.generation_status == "FAILED"
    assert result.error_message == "Could not connect to the Ollama service."


def test_timeout_returns_failed_result() -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    service = OllamaFeedbackGenerator(
        config=_settings(),
        transport=httpx.MockTransport(time_out),
    )

    result = asyncio.run(
        service.generate_feedback("Problem", "code", _evaluation(), "LOW")
    )

    assert result.generation_status == "FAILED"
    assert result.error_message == "The Ollama request timed out."


def test_http_error_returns_failed_result() -> None:
    service = OllamaFeedbackGenerator(
        config=_settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, text="unavailable")
        ),
    )

    result = asyncio.run(
        service.generate_feedback("Problem", "code", _evaluation(), "LOW")
    )

    assert result.generation_status == "FAILED"
    assert result.error_message == "Ollama returned HTTP 503."


def test_malformed_json_returns_failed_result() -> None:
    service = OllamaFeedbackGenerator(
        config=_settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"{not-json")
        ),
    )

    result = asyncio.run(
        service.generate_feedback("Problem", "code", _evaluation(), "LOW")
    )

    assert result.generation_status == "FAILED"
    assert result.error_message == "Ollama returned malformed JSON."


def test_invalid_json_shape_returns_failed_result() -> None:
    service = OllamaFeedbackGenerator(
        config=_settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"response": ["not", "text"]})
        ),
    )

    result = asyncio.run(
        service.generate_feedback("Problem", "code", _evaluation(), "LOW")
    )

    assert result.generation_status == "FAILED"
    assert result.error_message == "Ollama response did not contain text."


def test_ollama_settings_have_safe_defaults_and_positive_timeout() -> None:
    config = Settings(_env_file=None)

    assert config.OLLAMA_BASE_URL == "http://localhost:11434"
    assert config.OLLAMA_MODEL == "qwen2.5:3b"
    assert config.OLLAMA_TIMEOUT > 0

    with pytest.raises(ValueError):
        Settings(_env_file=None, OLLAMA_TIMEOUT=0)
