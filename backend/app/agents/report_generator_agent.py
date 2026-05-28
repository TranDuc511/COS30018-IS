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


DEFAULT_MODEL = "gpt-5.4"
DEFAULT_FALLBACK_MODEL = "gpt-5.4-mini"
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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error_output("OPENAI_API_KEY is not set.")

    try:
        from openai import OpenAI
    except ImportError:
        return _error_output("The openai package is not installed.")

    client = OpenAI(api_key=api_key)
    messages = _llm_messages(report_input)
    last_error = "Unknown validation error."

    for model in _candidate_models():
        for _ in range(MAX_SELF_CORRECTION_RETRIES + 1):
            content = ""
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
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


def _candidate_models() -> list[str]:
    configured_model = os.getenv("OPENAI_MODEL")
    if configured_model:
        return [configured_model]

    models = [DEFAULT_MODEL]
    fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
    if fallback_model and fallback_model not in models:
        models.append(fallback_model)
    return models


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

