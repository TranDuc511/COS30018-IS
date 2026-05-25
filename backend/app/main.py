from fastapi import FastAPI

app = FastAPI(title="COS30018 Restaurant Review Analysis API")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/reports")
def create_report() -> dict[str, str]:
    return {"status": "not_implemented"}

