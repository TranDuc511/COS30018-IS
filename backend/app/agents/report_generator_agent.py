import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.contracts import (
    Recommendation,
    ReportGeneratorInput,
    ReportOutput,
    RootCause,
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


def generate_report(report_input: dict, use_llm: bool = True) -> dict:
    try:
        validated_input = ReportGeneratorInput.model_validate(report_input)
    except ValidationError as exc:
        return _error_output(f"Invalid report generator input: {exc}")

    if use_llm:
        return _generate_report_with_llm(validated_input)

    return _generate_report_deterministically(validated_input)


def _generate_report_deterministically(report_input: ReportGeneratorInput) -> dict:
    root_causes = _root_causes_from_reasoning(report_input.reasoning_summary)
    key_findings = _key_findings(report_input, root_causes)
    limitations = _limitations(report_input)

    output = ReportOutput(
        business_name=report_input.business_name,
        sample_size=report_input.sample_size,
        executive_summary=_executive_summary(report_input, key_findings),
        key_findings=key_findings,
        root_causes=root_causes,
        recommendations=report_input.recommendations,
        limitations=limitations,
        status="success",
        error_detail=None,
    )
    return _dump_output(output)


def _generate_report_with_llm(report_input: ReportGeneratorInput) -> dict:
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

    messages = _llm_messages(report_input)
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
                output = ReportOutput.model_validate(payload)
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
                                "JSON matching the required report schema. Validation error: "
                                f"{last_error}"
                            ),
                        },
                    ]
                )
            except Exception as exc:
                last_error = str(exc)
                break

    return _error_output(
        "Report generator LLM call failed after trying configured models: "
        f"{last_error}"
    )


def _llm_messages(report_input: ReportGeneratorInput) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the Report Generator Agent for a restaurant review analysis "
                "system. Produce a concise business-owner report. Return only JSON "
                "with keys: title, business_name, sample_size, executive_summary, "
                "key_findings, root_causes, recommendations, limitations, status, "
                "error_detail. Use status='success' when the report is valid."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(_dump_model(report_input), ensure_ascii=True),
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


def _root_causes_from_reasoning(reasoning_summary: dict[str, Any]) -> list[RootCause]:
    root_causes = reasoning_summary.get("root_causes", [])
    if not isinstance(root_causes, list):
        return []

    valid_root_causes = []
    for root_cause in root_causes:
        try:
            valid_root_causes.append(RootCause.model_validate(root_cause))
        except ValidationError:
            continue
    return valid_root_causes


def _key_findings(
    report_input: ReportGeneratorInput,
    root_causes: list[RootCause],
) -> list[str]:
    findings = []
    patterns = report_input.reasoning_summary.get("patterns", [])
    sentiment_distribution = report_input.analysis_summary.get("sentiment_distribution")
    top_aspects = report_input.analysis_summary.get("top_aspects")

    if isinstance(sentiment_distribution, dict) and sentiment_distribution:
        findings.append(
            "Sentiment distribution: "
            + ", ".join(f"{key}: {value}" for key, value in sentiment_distribution.items())
        )

    if isinstance(top_aspects, list) and top_aspects:
        findings.append("Most discussed aspects: " + ", ".join(map(str, top_aspects[:5])))

    if isinstance(patterns, list):
        for pattern in patterns[:3]:
            description = pattern.get("description") if isinstance(pattern, dict) else None
            if description:
                findings.append(str(description))

    if root_causes:
        findings.append(f"Identified {len(root_causes)} likely root cause(s).")

    if report_input.recommendations:
        findings.append(
            f"Generated {len(report_input.recommendations)} prioritised recommendation(s)."
        )

    if not findings:
        findings.append("No major recurring pattern was provided by upstream agents.")

    return findings


def _executive_summary(
    report_input: ReportGeneratorInput,
    key_findings: list[str],
) -> str:
    if report_input.recommendations:
        top_recommendation = report_input.recommendations[0]
        return (
            f"{report_input.business_name} was analysed using "
            f"{report_input.sample_size} sampled review(s). The top action is: "
            f"{top_recommendation.action}"
        )

    return (
        f"{report_input.business_name} was analysed using "
        f"{report_input.sample_size} sampled review(s). "
        f"{key_findings[0]}"
    )


def _limitations(report_input: ReportGeneratorInput) -> list[str]:
    limitations = [
        "Findings are based on the selected review sample, not every Yelp review.",
        "Recommendations should be validated against restaurant operations before action.",
    ]
    if report_input.sample_size == 0:
        limitations.append("No review records were included in the report input.")
    return limitations


def _error_output(error_detail: str) -> dict:
    return _dump_output(
        ReportOutput(
            status="error",
            error_detail=error_detail,
        )
    )


def _dump_output(output: ReportOutput) -> dict:
    return _dump_model(output)


def _dump_model(model: Any) -> dict:
    return model.model_dump()

