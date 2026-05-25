# Backend

FastAPI backend for the COS30018 restaurant review analysis system.

## Planned Responsibilities

- Load and preprocess Yelp dataset files.
- Match restaurant names to Yelp `business_id` values.
- Randomly sample up to 100 review records.
- Run the LangGraph multi-agent pipeline.
- Return structured report data to the frontend.

## Start Later

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

