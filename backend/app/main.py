from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.research import parse_research_pack
from app.research.sample import sample_zip
from app.workbench.csv_preview import CSVPreviewRequest, preview_csv
from app.workbench.kline_preview import KlinePreviewRequest, preview_kline
from app.workbench.overview import build_overview
from app.workbench.plan_preview import PlanPreviewRequest, preview_plan

settings = get_settings()

app = FastAPI(
    title="Structure Swing Workbench API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "structure-swing-backend",
        "environment": settings.app_env,
    }


@app.get("/research/sample", tags=["research"])
def research_sample() -> dict[str, object]:
    """Display-only synthetic fixture; no remote TradingAgents or trade execution."""
    return parse_research_pack(sample_zip()).to_dict()


@app.get("/workbench/overview", tags=["workbench"])
def workbench_overview() -> dict[str, object]:
    return build_overview()


@app.post("/workbench/plan-preview", tags=["workbench"])
def workbench_plan_preview(payload: PlanPreviewRequest) -> dict[str, object]:
    """Preview selected rules for explicit user input; never approve execution."""
    return preview_plan(payload)


@app.post("/workbench/csv-preview", tags=["workbench"])
def workbench_csv_preview(payload: CSVPreviewRequest) -> dict[str, object]:
    """Validate an uploaded CSV in a disposable ledger; never persist it."""
    return preview_csv(payload)


@app.post("/workbench/kline-preview", tags=["workbench"])
def workbench_kline_preview(payload: KlinePreviewRequest) -> dict[str, object]:
    return preview_kline(payload)
