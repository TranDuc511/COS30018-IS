from app.agents.report_generator_agent import (
    _candidate_models,
    _completion_options,
    _llm_provider,
    generate_report,
)


def test_generate_report_builds_deterministic_report():
    result = generate_report(
        {
            "business_name": "Example Restaurant",
            "sample_size": 100,
            "analysis_summary": {
                "sentiment_distribution": {
                    "positive": 55,
                    "neutral": 20,
                    "negative": 25,
                },
                "top_aspects": ["wait_time", "pricing"],
            },
            "reasoning_summary": {
                "patterns": [
                    {
                        "description": "Wait-time complaints appear repeatedly.",
                        "aspect": "wait_time",
                        "frequency": 0.42,
                        "evidence_review_ids": ["r1", "r2"],
                    }
                ],
                "root_causes": [
                    {
                        "pattern": "Repeated wait-time complaints",
                        "cause": "Possible staffing or table-turnover issue during busy periods",
                        "confidence": "high",
                    }
                ],
            },
            "recommendations": [
                {
                    "priority": 1,
                    "issue": "Possible staffing or table-turnover issue during busy periods",
                    "action": "Review peak-hour staffing and table assignment workflow.",
                    "category": "operations",
                    "expected_impact": "Reduce wait-time complaints",
                }
            ],
        },
        use_llm=False,
    )

    assert result["status"] == "success"
    assert result["error_detail"] is None
    assert result["title"] == "Restaurant Review Analysis Report"
    assert result["business_name"] == "Example Restaurant"
    assert result["sample_size"] == 100
    assert "Review peak-hour staffing" in result["executive_summary"]
    assert result["root_causes"][0]["confidence"] == "high"
    assert result["recommendations"][0]["priority"] == 1
    assert result["limitations"]


def test_generate_report_handles_empty_upstream_outputs():
    result = generate_report(
        {
            "business_name": "Empty Restaurant",
            "sample_size": 0,
            "analysis_summary": {},
            "reasoning_summary": {},
            "recommendations": [],
        },
        use_llm=False,
    )

    assert result["status"] == "success"
    assert result["recommendations"] == []
    assert result["root_causes"] == []
    assert result["key_findings"] == [
        "No major recurring pattern was provided by upstream agents."
    ]
    assert "No review records" in result["limitations"][-1]


def test_generate_report_returns_error_for_invalid_input():
    result = generate_report(
        {
            "business_name": "Bad Input Restaurant",
            "sample_size": -1,
            "analysis_summary": {},
            "reasoning_summary": {},
            "recommendations": [],
        },
        use_llm=False,
    )

    assert result["status"] == "error"
    assert result["recommendations"] == []
    assert "Invalid report generator input" in result["error_detail"]


def test_generate_report_requires_api_key_for_llm_mode(monkeypatch):
    monkeypatch.setattr("app.agents.report_generator_agent._load_environment", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = generate_report(
        {
            "business_name": "Example Restaurant",
            "sample_size": 10,
            "analysis_summary": {},
            "reasoning_summary": {},
            "recommendations": [],
        },
        use_llm=True,
    )

    assert result["status"] == "error"
    assert result["recommendations"] == []
    assert result["error_detail"] == "OPENAI_API_KEY is not set."


def test_report_candidate_models_use_configured_primary_and_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-5-mini")

    assert _candidate_models() == ["gpt-5", "gpt-5-mini"]


def test_report_candidate_models_support_gemini_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)

    assert _candidate_models() == ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]


def test_report_gemini_completion_options_use_low_reasoning_by_default(monkeypatch):
    monkeypatch.delenv("GEMINI_REASONING_EFFORT", raising=False)

    assert _completion_options("gemini")["reasoning_effort"] == "low"


def test_report_unknown_provider_is_reported(monkeypatch):
    monkeypatch.setattr("app.agents.report_generator_agent._load_environment", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    assert _llm_provider() == "unknown"

    result = generate_report(
        {
            "business_name": "Example Restaurant",
            "sample_size": 10,
            "analysis_summary": {},
            "reasoning_summary": {},
            "recommendations": [],
        },
        use_llm=True,
    )

    assert result["status"] == "error"
    assert "Unsupported LLM_PROVIDER" in result["error_detail"]
