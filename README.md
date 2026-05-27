# COS30018 Intelligent Systems

## Multi-Agent System for Restaurant Review Analysis

This project builds a Python-based multi-agent AI system for F&B business owners.
Given a restaurant name, the system searches the Yelp Open Dataset, randomly selects
up to 100 matching review records, analyses the feedback, identifies recurring
patterns, and generates an actionable business report.

The goal is to turn raw restaurant feedback into clear operational recommendations
without requiring the owner to manually process review text.

## Repository Structure

```text
COS30018-IS/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── core/
│   │   ├── data/
│   │   ├── schemas/
│   │   └── main.py
│   ├── data/
│   │   ├── raw/
│   │   └── processed/
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   └── package.json
├── .gitignore
├── AGENTS.md
└── README.md
```

Team members should read `AGENTS.md` before changing architecture, agent
contracts, data handling, or repository structure.

## 1. Project Overview

Restaurant owners often receive more review data than they can realistically read.
Important business signals can be buried inside unstructured text, such as repeated
complaints about wait time, staff attitude, pricing, food quality, or ambience.

This system automates the pipeline from restaurant lookup to final report:

1. Match a restaurant name against the Yelp dataset.
2. Randomly sample up to 100 review records for that restaurant.
3. Classify sentiment and business aspects in each selected review.
4. Detect patterns across the analysed sample.
5. Infer likely root causes.
6. Produce prioritised recommendations.
7. Generate a readable web report for the business owner.

## 2. Problem Statement

Restaurant feedback is useful, but raw review text is hard to use at scale.
Owners may miss repeated issues because the feedback is scattered across many
individual comments.

This project addresses three problems:

- Recurring complaints are difficult to detect manually.
- Root causes are not obvious from individual reviews.
- Owners need prioritised actions, not only sentiment summaries.

## 3. Proposed Solution

The system uses a supervisor-based multi-agent collaboration pattern with
LangGraph. An Orchestrator Agent manages shared pipeline state, routes work between
specialised agents, validates outputs, and handles failures.

LLM-powered agents use `gpt-5.4` as the primary model and `gpt-5.4-mini` as the
fallback model for generation and correction. If the account does not have access
to those models, configure `OPENAI_MODEL=gpt-5` and
`OPENAI_FALLBACK_MODEL=gpt-5-mini`. Each agent must validate its own output
against a JSON schema before passing results back to the Orchestrator.

## 4. User Flow

This section is reserved for a future user-flow diagram.

Planned flow:

1. User enters restaurant name.
2. System returns possible business matches if the name is ambiguous.
3. User confirms the correct restaurant.
4. System randomly selects up to 100 review records.
5. Agents analyse the selected sample.
6. System generates the final web report.

## 5. Data Source

The project uses the Yelp Open Dataset from Kaggle.

Required files:

- `business.json`: used to resolve a restaurant name to a `business_id`.
- `review.json`: used to retrieve review records for the selected `business_id`.

The dataset contains millions of reviews, so the system must not load or process
the full dataset inside the LLM pipeline. After matching a restaurant, the system
randomly samples a maximum of 100 review records for analysis.

## 6. Dataset Plan

This section is reserved for the detailed implementation plan.

Planned approach:

- Store preprocessed business and review data in SQLite or Parquet.
- Create an index on `business_id` for fast review lookup.
- Create a searchable restaurant-name field for fuzzy matching.
- Return the top 3 restaurant matches when the input name is ambiguous.
- Randomly sample up to 100 review records after a restaurant is confirmed.
- Keep the random seed configurable so demo results can be reproduced.
- Pass only the selected sample into the agent pipeline.

## 7. System Architecture

The system follows a Supervisor / Multi-Agent Collaboration architecture.

The Orchestrator Agent is responsible for:

- Managing the shared pipeline state.
- Calling each agent in the correct order.
- Validating agent status values.
- Handling retries, skips, and halt conditions.
- Returning partial output when the full pipeline cannot complete.

Agent sequence:

1. Data Pipeline
2. Analysis Agent
3. Reasoning Agent
4. Strategic Agent
5. Report Generator Agent

## 8. Agent Roles

| Agent | Role | LLM | Responsibility |
| --- | --- | --- | --- |
| Orchestrator Agent | Supervisor | `gpt-5.4` / `gpt-5.4-mini` | Routes work, checks status, handles failures, retries agents, skips non-critical steps, or halts with partial output. |
| Analysis Agent | Review analysis | `gpt-5.4` / `gpt-5.4-mini` | Classifies each selected review by sentiment and aspect. Runs once per sampled review. |
| Reasoning Agent | Pattern and root-cause reasoning | `gpt-5.4` / `gpt-5.4-mini` | Detects recurring patterns across the analysed sample and proposes likely root causes. |
| Strategic Agent | Recommendation generation | `gpt-5.4` / `gpt-5.4-mini` | Converts root causes into prioritised business actions. |
| Report Generator Agent | Final report generation | `gpt-5.4` / `gpt-5.4-mini` | Produces a structured human-readable web report from upstream outputs. |

## 9. Data Flow Summary

```text
Yelp Dataset
-> Preprocessing
-> Restaurant fuzzy match
-> Random sample, max 100 reviews
-> Pandas DataFrame
-> Orchestrator Agent
-> Analysis Agent
-> Reasoning Agent
-> Strategic Agent
-> Report Generator Agent
-> Web Report
```

All agent communication uses structured JSON payloads. The Orchestrator validates
each agent output before routing to the next step.

## 10. Autonomous Error Handling

The system uses a two-layer error-handling pattern.

### 10.1 Layer 1: Agent Self-Correction

Each LLM-powered agent validates its own JSON output immediately after generation.
If validation fails, the agent retries with a correction prompt that includes:

- The original task.
- The invalid output.
- The validation error.
- The required schema.

Each agent may retry a maximum of 2 times. If the output is still invalid after
2 retries, the agent returns `status: "error"` and passes the error details to the
Orchestrator.

### 10.2 Layer 2: Orchestrator Intervention

If an agent cannot self-correct, the Orchestrator chooses one of three strategies:

| Strategy | When to use | Behaviour |
| --- | --- | --- |
| Retry with simplified prompt | The output is close to valid but still fails schema validation. | The Orchestrator rewrites the prompt with stricter constraints and retries the same agent. |
| Skip agent and flag state | The failed agent is non-critical and the pipeline can continue with partial data. | The Orchestrator marks the step as skipped and downstream agents receive `null` for that input. |
| Halt and return partial report | A critical agent fails and meaningful output cannot be produced. | The Orchestrator stops the pipeline and returns a partial report with a clear error message. |

## 11. Interface Contracts

These contracts define the expected inputs and outputs for each component. They
should not be changed without team agreement because downstream agents depend on
them.

### 11.1 Preprocessed Review Record

```json
{
  "review_id": "abc123",
  "business_id": "business_001",
  "stars": 4,
  "text": "Food was good but the wait was too long.",
  "date": "2024-05-10"
}
```

### 11.2 Analysis Agent Input

```json
{
  "review_id": "abc123",
  "stars": 4,
  "text": "Food was good but the wait was too long.",
  "date": "2024-05-10"
}
```

### 11.3 Analysis Agent Output

```json
{
  "review_id": "abc123",
  "sentiment": "mixed",
  "aspects": [
    {
      "category": "food_quality",
      "label": "positive"
    },
    {
      "category": "wait_time",
      "label": "negative"
    }
  ],
  "status": "success",
  "error_detail": null
}
```

Allowed sentiment values:

- `positive`
- `negative`
- `neutral`
- `mixed`

Allowed aspect categories:

- `food_quality`
- `staff_attitude`
- `pricing`
- `wait_time`
- `ambience`
- `cleanliness`
- `other`

### 11.4 Reasoning Agent Input

```json
{
  "business_id": "business_001",
  "sample_size": 100,
  "analysis_results": [
    {
      "review_id": "abc123",
      "sentiment": "mixed",
      "aspects": [
        {
          "category": "food_quality",
          "label": "positive"
        },
        {
          "category": "wait_time",
          "label": "negative"
        }
      ]
    }
  ]
}
```

### 11.5 Reasoning Agent Output

```json
{
  "patterns": [
    {
      "description": "Wait-time complaints appear repeatedly in the selected sample.",
      "aspect": "wait_time",
      "frequency": 0.42,
      "evidence_review_ids": ["abc123", "abc456"]
    }
  ],
  "root_causes": [
    {
      "pattern": "Repeated wait-time complaints",
      "cause": "Possible staffing or table-turnover issue during busy periods",
      "confidence": "medium"
    }
  ],
  "status": "success",
  "error_detail": null
}
```

### 11.6 Strategic Agent Input

```json
{
  "patterns": [],
  "root_causes": []
}
```

### 11.7 Strategic Agent Output

```json
{
  "recommendations": [
    {
      "priority": 1,
      "issue": "Possible staffing or table-turnover issue during busy periods",
      "action": "Review weekend staffing levels and table assignment workflow.",
      "category": "operations",
      "expected_impact": "Reduce wait-time complaints"
    }
  ],
  "status": "success",
  "error_detail": null
}
```

### 11.8 Report Generator Agent Input

```json
{
  "business_name": "Example Restaurant",
  "sample_size": 100,
  "analysis_summary": {},
  "reasoning_summary": {},
  "recommendations": []
}
```

### 11.9 Report Output Schema

This section is reserved for the final report schema.

Draft schema:

```json
{
  "title": "Restaurant Review Analysis Report",
  "business_name": "Example Restaurant",
  "sample_size": 100,
  "executive_summary": "Short plain-English summary.",
  "key_findings": [],
  "root_causes": [],
  "recommendations": [],
  "limitations": [],
  "status": "success",
  "error_detail": null
}
```

### 11.10 Error Schema

This section is reserved for the final error schema.

Draft schema:

```json
{
  "status": "error",
  "agent": "analysis_agent",
  "error_type": "schema_validation_error",
  "error_detail": "Missing required field: sentiment",
  "retry_count": 2,
  "recoverable": true
}
```

### 11.11 Orchestrator State Schema

This section is reserved for the final Orchestrator state schema.

Draft schema:

```json
{
  "business_id": "business_001",
  "business_name": "Example Restaurant",
  "sample_size": 100,
  "selected_reviews": [],
  "analysis_results": [],
  "reasoning_result": null,
  "strategy_result": null,
  "report_result": null,
  "retry_counts": {
    "analysis_agent": 0,
    "reasoning_agent": 0,
    "strategic_agent": 0,
    "report_generator_agent": 0
  },
  "skipped_agents": [],
  "errors": [],
  "status": "running"
}
```

## 12. Technology Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.10+ |
| Agent framework | LangChain + LangGraph |
| LLM | OpenAI `gpt-5.4` primary, `gpt-5.4-mini` fallback |
| Data processing | Pandas |
| Business-name matching | Fuzzy matching library such as RapidFuzz |
| Dataset | Yelp Open Dataset from Kaggle |
| Backend | FastAPI |
| UI | React or Streamlit |
| Output | Web report / dashboard |

Note: Streamlit is simpler for the prototype. React can be used if the team wants
a more polished dashboard, but it increases implementation work.

## 13. Milestones

| Phase | Target | Deliverable |
| --- | --- | --- |
| Phase 0 | 25/05 | Project brief reviewed, scope confirmed, interface contracts drafted. |
| Phase 1 | 05/06 | Components working in isolation against mock data, including output validators and self-correction prompts. |
| Phase 2 | 17/06 | Full pipeline running with Yelp data and random sample of up to 100 reviews. Error handling tested with malformed outputs. |
| Phase 3 | 30/06 | Web report polished, recovery strategies tested, final demo prepared. |

## 14. Evaluation Plan

This section is reserved for future evaluation criteria.

Planned evaluation areas:

- Sentiment and aspect classification quality.
- JSON schema validity rate.
- Agent retry success rate.
- Pipeline completion rate.
- Runtime and LLM cost for up to 100 reviews.
- Usefulness of the final report.

## 15. Key Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Restaurant name is ambiguous or not found | Return top 3 fuzzy matches and ask the user to confirm. |
| Dataset is too large to process directly | Preprocess into SQLite or Parquet and query by `business_id`. |
| LLM cost is too high | Randomly sample up to 100 reviews and keep the cap configurable. |
| Agent output is invalid | Validate every JSON output and allow up to 2 self-correction retries. |
| Agent enters repeated failure loop | Track retry counts in Orchestrator state and halt or skip after limits are reached. |
| Downstream agents receive missing data | Require downstream agents to handle `null` input and produce partial output when possible. |
