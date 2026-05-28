from app.agents.strategic_agent import (
    _candidate_models,
    _completion_options,
    _llm_provider,
    generate_recommendations,
)


def test_generate_recommendations_prioritizes_confidence_and_frequency():
    result = generate_recommendations(
        {
            "patterns": [
                {
                    "description": "Repeated wait-time complaints",
                    "aspect": "wait_time",
                    "frequency": 0.42,
                    "evidence_review_ids": ["r1", "r2"],
                },
                {
                    "description": "Pricing complaints",
                    "aspect": "pricing",
                    "frequency": 0.25,
                    "evidence_review_ids": ["r3"],
                },
            ],
            "root_causes": [
                {
                    "pattern": "Pricing complaints",
                    "cause": "Menu prices may not match customer value expectations",
                    "confidence": "medium",
                },
                {
                    "pattern": "Repeated wait-time complaints",
                    "cause": "Possible staffing or table-turnover issue during busy periods",
                    "confidence": "high",
                },
            ],
        },
        use_llm=False,
    )

    assert result["status"] == "success"
    assert result["error_detail"] is None
    assert len(result["recommendations"]) == 2
    assert result["recommendations"][0]["priority"] == 1
    assert result["recommendations"][0]["category"] == "operations"
    assert "staffing" in result["recommendations"][0]["issue"]
    assert result["recommendations"][1]["priority"] == 2
    assert result["recommendations"][1]["category"] == "pricing"


def test_generate_recommendations_allows_empty_root_causes():
    result = generate_recommendations(
        {"patterns": [], "root_causes": []},
        use_llm=False,
    )

    assert result == {
        "recommendations": [],
        "status": "success",
        "error_detail": None,
    }


def test_generate_recommendations_returns_error_for_invalid_input():
    result = generate_recommendations(
        {"patterns": "not-a-list", "root_causes": []},
        use_llm=False,
    )

    assert result["status"] == "error"
    assert result["recommendations"] == []
    assert "Invalid strategic agent input" in result["error_detail"]


def test_generate_recommendations_requires_api_key_for_llm_mode(monkeypatch):
    monkeypatch.setattr("app.agents.strategic_agent._load_environment", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = generate_recommendations(
        {
            "patterns": [],
            "root_causes": [
                {
                    "pattern": "Repeated wait-time complaints",
                    "cause": "Possible staffing issue",
                    "confidence": "high",
                }
            ],
        },
        use_llm=True,
    )

    assert result["status"] == "error"
    assert result["recommendations"] == []
    assert result["error_detail"] == "OPENAI_API_KEY is not set."


def test_candidate_models_use_primary_and_fallback_defaults(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_FALLBACK_MODEL", raising=False)

    assert _candidate_models() == ["gpt-5.4", "gpt-5.4-mini"]


def test_candidate_models_allow_explicit_primary_override(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-5-mini")

    assert _candidate_models() == ["gpt-5", "gpt-5-mini"]


def test_candidate_models_support_gemini_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)

    assert _candidate_models() == ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]


def test_candidate_models_allow_explicit_gemini_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")

    assert _candidate_models() == ["gemini-3.1-flash-lite", "gemini-2.5-flash"]


def test_gemini_completion_options_use_low_reasoning_by_default(monkeypatch):
    monkeypatch.delenv("GEMINI_REASONING_EFFORT", raising=False)

    assert _completion_options("gemini")["reasoning_effort"] == "low"


def test_unknown_provider_is_reported(monkeypatch):
    monkeypatch.setattr("app.agents.strategic_agent._load_environment", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    assert _llm_provider() == "unknown"

    result = generate_recommendations(
        {
            "patterns": [],
            "root_causes": [
                {
                    "pattern": "Repeated wait-time complaints",
                    "cause": "Possible staffing issue",
                    "confidence": "high",
                }
            ],
        },
        use_llm=True,
    )

    assert result["status"] == "error"
    assert "Unsupported LLM_PROVIDER" in result["error_detail"]
