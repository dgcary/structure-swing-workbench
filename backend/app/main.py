from ipaddress import ip_address
from secrets import compare_digest

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import build_engine
from app.research import parse_research_pack
from app.research.sample import sample_zip
from app.workbench.account_snapshot_preview import (
    AccountSnapshotPreviewRequest,
    preview_account_snapshot,
)
from app.workbench.action_date import ActionDateRequest, update_action_planned_date
from app.workbench.csv_preview import CSVPreviewRequest, preview_csv
from app.workbench.kline_preview import KlinePreviewRequest, preview_kline
from app.workbench.overview import build_overview
from app.workbench.persisted import project_persisted
from app.workbench.plan_preview import PlanPreviewRequest, preview_plan
from app.workbench.t_cycle_preview import TCyclePreviewRequest, preview_t_cycle

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
    if not settings.workbench_persisted_read_enabled:
        return build_overview()
    try:
        engine = build_engine()
        try:
            with Session(engine) as session:
                persisted = project_persisted(session)
        finally:
            engine.dispose()
        return build_overview(persisted=persisted)
    except SQLAlchemyError:
        # No partial DB facts may masquerade as an available account.
        result = build_overview()
        result["notice"] += " 持久化数据源不可用；请检查数据库连接与迁移。"
        return result


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


@app.post("/workbench/account-snapshot-preview", tags=["workbench"])
def workbench_account_snapshot_preview(
    payload: AccountSnapshotPreviewRequest,
) -> dict[str, object]:
    """Show uploaded account CSVs only in an isolated request-scoped ledger."""
    return preview_account_snapshot(payload)


@app.post("/workbench/t-cycle-preview", tags=["workbench"])
def workbench_t_cycle_preview(payload: TCyclePreviewRequest) -> dict[str, object]:
    """Calculate one user-supplied T cycle without broker or execution access."""
    return preview_t_cycle(payload)


def _trusted_date_write_transport(request: Request) -> bool:
    """Never accept a privileged bearer date edit over remote plaintext HTTP.

    The ASGI scheme must already reflect a trusted TLS terminator. Do not
    trust a caller-supplied X-Forwarded-Proto header inside this handler.
    """
    if request.url.scheme == "https":
        return True
    if request.url.scheme != "http" or request.client is None:
        return False
    try:
        peer = ip_address(request.client.host)
        host = request.url.hostname
        local_host = host == "localhost" or (
            host is not None and ip_address(host).is_loopback
        )
    except ValueError:
        return False
    return peer.is_loopback and local_host


@app.put("/workbench/actions/{action_id}/planned-date", tags=["workbench"])
def workbench_update_action_date(
    action_id: str, payload: ActionDateRequest, request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    """Opt-in, bearer-protected date-only correction; never execute an action."""
    if not (settings.workbench_persisted_read_enabled
            and settings.workbench_action_date_write_enabled):
        raise HTTPException(status_code=404, detail="正式动作日期修改功能未启用")
    if not _trusted_date_write_transport(request):
        raise HTTPException(status_code=403, detail="正式动作日期修改仅允许 HTTPS 或本机回环访问")
    secret = settings.workbench_action_date_write_token
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="管理员令牌未安全配置")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not authorization or not authorization.startswith("Bearer ") or not compare_digest(
        supplied, secret
    ):
        raise HTTPException(
            status_code=401, detail="管理员令牌无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        engine = build_engine()
        try:
            with Session(engine) as session:
                result = update_action_planned_date(session, action_id, payload)
                session.commit()
                return result
        finally:
            engine.dispose()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="正式动作数据库暂不可用") from exc
