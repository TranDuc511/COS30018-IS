import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.contracts import (
    Pattern,
    Recommendation,
    RootCause,
    StrategicAgentInput,
    StrategicAgentOutput,
)


OPENAI_PROVIDER = "openai"

# Temporary live-agent testing only. Gemini is not part of the production project
# plan and should be removed after fallback testing is finished.
GEMINI_PROVIDER = "gemini"
DEFAULT_PROVIDER = OPENAI_PROVIDER
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENAI_FALLBACK_MODEL = "gpt-5.4-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_REASONING_EFFORT = "low"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_SELF_CORRECTION_RETRIES = 2


def generate_recommendations(reasoning_result: dict, use_llm: bool = True) -> dict:
    try:
        strategic_input = StrategicAgentInput.model_validate(reasoning_result)
    except ValidationError as exc:
        return _error_output(f"Invalid strategic agent input: {exc}")

    if not strategic_input.root_causes:
        return _dump_output(
            StrategicAgentOutput(
                recommendations=[],
                status="success",
                error_detail=None,
            )
        )

    if use_llm:
        return _generate_recommendations_with_llm(strategic_input)

    return _generate_recommendations_deterministically(strategic_input)


def _generate_recommendations_deterministically(
    strategic_input: StrategicAgentInput,
) -> dict:
    ranked_root_causes = sorted(
        strategic_input.root_causes,
        key=lambda root_cause: _priority_score(root_cause, strategic_input.patterns),
        reverse=True,
    )

    recommendations = [
        Recommendation(
            priority=index,
            issue=root_cause.cause,
            action=_action_for_root_cause(root_cause),
            category=_category_for_root_cause(root_cause),
            expected_impact=_expected_impact_for_root_cause(root_cause),
        )
        for index, root_cause in enumerate(ranked_root_causes, start=1)
    ]

    return _dump_output(
        StrategicAgentOutput(
            recommendations=recommendations,
            status="success",
            error_detail=None,
        )
    )


def _generate_recommendations_with_llm(strategic_input: StrategicAgentInput) -> dict:
    _load_environment()
    provider = _llm_provider()
    if provider not in {OPENAI_PROVIDER, GEMINI_PROVIDER}:
        return _error_output(
            f"Unsupported LLM_PROVIDER '{provider}'. Use 'openai' or 'gemini'."
        )

    try:
        from openai import OpenAI
    except ImportError:
        return _error_output("The openai package is not installed.")

    client = _llm_client(OpenAI, provider)
    if isinstance(client, str):
        return _error_output(client)

    messages = _llm_messages(strategic_input)
    last_error = "Unknown validation error."

    for model in _candidate_models(provider):
        for _ in range(MAX_SELF_CORRECTION_RETRIES + 1):
            content = ""
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **_completion_options(provider),
                )
                content = response.choices[0].message.content or "{}"
                payload = json.loads(content)
                output = StrategicAgentOutput.model_validate(payload)
                return _dump_output(output)
            except (json.JSONDecodeError, ValidationError, KeyError, IndexError) as exc:
                last_error = str(exc)
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": content,
                        },
                        {
                            "role": "user",
                            "content": (
                                "The previous output failed validation. Return only valid "
                                "JSON matching the required schema. Validation error: "
                                f"{last_error}"
                            ),
                        },
                    ]
                )
            except Exception as exc:
                last_error = str(exc)
                break

    return _error_output(
        "Strategic agent LLM call failed after trying configured models: "
        f"{last_error}"
    )


def _llm_messages(strategic_input: StrategicAgentInput) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the Strategic Agent for a restaurant review analysis system. "
                "Convert root causes into prioritized business actions. Return only "
                "JSON with keys: recommendations, status, error_detail. Every "
                "recommendation must contain priority, issue, action, category, and "
                "expected_impact. Use status='success' when recommendations are valid."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(_dump_model(strategic_input), ensure_ascii=True),
        },
    ]


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env")
    load_dotenv()


def _llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).lower().strip()


def _llm_client(openai_client: Any, provider: str) -> Any:
    if provider == GEMINI_PROVIDER:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "GEMINI_API_KEY is not set."
        return openai_client(api_key=api_key, base_url=GEMINI_OPENAI_BASE_URL)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "OPENAI_API_KEY is not set."
    return openai_client(api_key=api_key)


def _candidate_models(provider: str | None = None) -> list[str]:
    provider = provider or _llm_provider()

    if provider == GEMINI_PROVIDER:
        primary_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        models = [primary_model]
        fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_GEMINI_FALLBACK_MODEL)
        if fallback_model and fallback_model not in models:
            models.append(fallback_model)
        return models

    primary_model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    models = [primary_model]
    fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", DEFAULT_OPENAI_FALLBACK_MODEL)
    if fallback_model and fallback_model not in models:
        models.append(fallback_model)
    return models


def _completion_options(provider: str) -> dict[str, Any]:
    options = {
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    if provider == GEMINI_PROVIDER:
        options["reasoning_effort"] = os.getenv(
            "GEMINI_REASONING_EFFORT",
            DEFAULT_GEMINI_REASONING_EFFORT,
        )
    return options


def _priority_score(root_cause: RootCause, patterns: list[Pattern]) -> float:
    confidence_score = {"high": 3, "medium": 2, "low": 1}[root_cause.confidence]
    related_frequency = max(
        (
            pattern.frequency
            for pattern in patterns
            if _same_topic(root_cause.pattern, pattern.description)
        ),
        default=0,
    )
    return confidence_score + related_frequency


def _same_topic(root_pattern: str, pattern_description: str) -> bool:
    left = root_pattern.lower().strip()
    right = pattern_description.lower().strip()
    return bool(left and right and (left in right or right in left))


def _category_for_root_cause(root_cause: RootCause) -> str:
    text = f"{root_cause.pattern} {root_cause.cause}".lower()
    if any(keyword in text for keyword in ["wait", "queue", "table", "turnover"]):
        return "operations"
    if any(keyword in text for keyword in ["staff", "service", "rude", "attitude"]):
        return "service"
    if any(keyword in text for keyword in ["price", "pricing", "expensive", "value"]):
        return "pricing"
    if any(keyword in text for keyword in ["food", "taste", "cold", "portion", "menu"]):
        return "food_quality"
    if any(keyword in text for keyword in ["ambience", "noise", "music", "atmosphere"]):
        return "ambience"
    if any(keyword in text for keyword in ["clean", "dirty", "hygiene"]):
        return "cleanliness"
    return "operations"


def _action_for_root_cause(root_cause: RootCause) -> str:
    category = _category_for_root_cause(root_cause)
    actions = {
        "operations": "Review peak-hour staffing, table assignment, and handoff workflows linked to this issue.",
        "service": "Coach front-of-house staff on service recovery, tone, and escalation for repeated complaint scenarios.",
        "pricing": "Audit menu pricing, portion value, and customer-facing explanations for items mentioned in complaints.",
        "food_quality": "Check preparation consistency, holding times, and quality control for the affected menu items.",
        "ambience": "Review dining-room noise, seating layout, lighting, and atmosphere factors mentioned in reviews.",
        "cleanliness": "Increase inspection frequency and assign clear ownership for cleanliness checkpoints.",
    }
    return actions.get(category, "Investigate the root cause and assign an owner for corrective action.")


def _expected_impact_for_root_cause(root_cause: RootCause) -> str:
    category = _category_for_root_cause(root_cause)
    impacts = {
        "operations": "Reduce operational complaints and improve guest throughput.",
        "service": "Improve perceived service quality and reduce negative staff-related reviews.",
        "pricing": "Improve value perception and reduce price-related dissatisfaction.",
        "food_quality": "Improve food consistency and reduce menu-item complaints.",
        "ambience": "Improve dining experience and reduce environment-related complaints.",
        "cleanliness": "Reduce cleanliness complaints and protect customer trust.",
    }
    return impacts.get(category, "Reduce repeated complaints connected to the identified root cause.")


def _error_output(error_detail: str) -> dict:
    return _dump_output(
        StrategicAgentOutput(
            recommendations=[],
            status="error",
            error_detail=error_detail,
        )
    )


def _dump_output(output: StrategicAgentOutput) -> dict:
    return _dump_model(output)


def _dump_model(model: Any) -> dict:
    return model.model_dump()
