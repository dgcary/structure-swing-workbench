import json
from ipaddress import ip_address
from secrets import compare_digest
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
from app.workbench.dongwu_statement import check_dongwu_statement_pdf
from app.workbench.kline_preview import KlinePreviewRequest, preview_kline
from app.workbench.manual_journal import (
    ManualJournalConflict,
    ManualJournalWrite,
    ManualOperationApply,
    append_manual_record,
    apply_manual_operation,
    read_manual_records,
)
from app.workbench.overview import build_overview
from app.workbench.persisted import project_persisted
from app.workbench.plan_preview import PlanPreviewRequest, preview_plan
from app.workbench.t_cycle_preview import TCyclePreviewRequest, preview_t_cycle

settings = get_settings()
MAX_STATEMENT_UPLOAD_BYTES = 10_000_000
MAX_MANUAL_JOURNAL_BYTES = 100_000

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


def _local_statement_transport(request: Request) -> bool:
    """Require a loopback URL and peer; remote proxies must not expose PDF upload."""
    if request.client is None:
        return False
    try:
        host = request.url.hostname
        local_host = host == "localhost" or (
            host is not None and ip_address(host).is_loopback
        )
        origin = urlsplit(request.headers.get("origin", ""))
        origin_host = origin.hostname
        local_origin = origin_host == "localhost" or (
            origin_host is not None and ip_address(origin_host).is_loopback
        )
        return (
            local_host and ip_address(request.client.host).is_loopback
            and origin.scheme in {"http", "https"} and local_origin
            and not origin.username and not origin.password
            and not origin.path and not origin.query and not origin.fragment
        )
    except ValueError:
        return False


@app.post("/workbench/dongwu-statement-check", tags=["workbench"])
async def workbench_dongwu_statement_check(request: Request) -> dict[str, object]:
    """Check a user-selected PDF in memory; never save or publish account facts."""
    if not settings.workbench_statement_check_enabled:
        raise HTTPException(status_code=404, detail="本机对账单核对未启用")
    host = settings.app_host
    try:
        bound_locally = host == "localhost" or ip_address(host).is_loopback
    except ValueError:
        bound_locally = False
    if not bound_locally or not _local_statement_transport(request):
        raise HTTPException(status_code=403, detail="对账单核对仅允许本机回环访问")
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/pdf":
        raise HTTPException(status_code=415, detail="仅支持已解压的 PDF 文件")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_STATEMENT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PDF 超过本机核对大小上限")
        chunks.append(chunk)
    try:
        check = check_dongwu_statement_pdf(b"".join(chunks))
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail="本机 PDF 核对组件未安装") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="对账单无法按已核实格式核对") from exc
    return {
        "schema_version": "m8.dongwu_statement_check.v1",
        "mode": "local_pdf_preview",
        "notice": "仅核对所选账单内部一致性；非实时账户、非券商全量认证，不保存或授权交易。",
        "status": check.status,
        "period_start": check.period_start.isoformat(),
        "period_end": check.period_end.isoformat(),
        "summary_row_count": check.summary_row_count,
        "detail_row_count": check.detail_row_count,
        "matched_group_count": check.matched_group_count,
        "missing_summary_group_count": check.missing_summary_group_count,
        "extra_summary_group_count": check.extra_summary_group_count,
        "mismatched_group_count": check.mismatched_group_count,
        "repaired_summary_rows": check.repaired_summary_rows,
        "broker_reconciled": check.broker_reconciled,
        "full_account_verified": check.full_account_verified,
        "trade_execution_enabled": check.trade_execution_enabled,
        "execution_ids_available": check.execution_ids_available,
        "execution_times_available": check.execution_times_available,
        "footer_totals_checked": check.footer_totals_checked,
        "footer_totals_mismatched_count": check.footer_totals_mismatched_count,
    }


@app.post("/workbench/t-cycle-preview", tags=["workbench"])
def workbench_t_cycle_preview(payload: TCyclePreviewRequest) -> dict[str, object]:
    """Calculate one user-supplied T cycle without broker or execution access."""
    return preview_t_cycle(payload)


def _manual_journal_access(request: Request, journal_token: str | None) -> None:
    if not settings.workbench_manual_journal_enabled:
        raise HTTPException(status_code=404, detail="手工台账未启用")
    if not _trusted_date_write_transport(request):
        raise HTTPException(status_code=403, detail="手工台账仅允许可信 HTTPS 或本机访问")
    secret = settings.workbench_manual_journal_token
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="手工台账访问令牌未安全配置")
    if not journal_token or not compare_digest(journal_token, secret):
        raise HTTPException(status_code=401, detail="手工台账访问令牌无效")


@app.get("/workbench/manual-journal", tags=["workbench"])
def workbench_manual_journal_read(
    request: Request,
    journal_token: str | None = Header(default=None, alias="X-Workbench-Journal-Token"),
) -> dict[str, object]:
    _manual_journal_access(request, journal_token)
    try:
        engine = build_engine()
        try:
            with Session(engine) as session:
                return read_manual_records(session)
        finally:
            engine.dispose()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="手工台账数据库暂不可用") from exc


@app.post("/workbench/manual-journal", tags=["workbench"], status_code=201)
async def workbench_manual_journal_save(
    request: Request,
    journal_token: str | None = Header(default=None, alias="X-Workbench-Journal-Token"),
) -> dict[str, object]:
    _manual_journal_access(request, journal_token)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_MANUAL_JOURNAL_BYTES:
            raise HTTPException(status_code=413, detail="手工台账记录过大")
        chunks.append(chunk)
    try:
        payload = ManualJournalWrite.model_validate(json.loads(b"".join(chunks)))
    except (ValidationError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="手工台账字段无效") from exc
    if payload.operation is not None:
        raise HTTPException(status_code=422, detail="买卖操作须由自动更新持仓接口登记")
    try:
        engine = build_engine()
        try:
            with Session(engine) as session:
                result = append_manual_record(session, payload)
                session.commit()
                return result
        finally:
            engine.dispose()
    except ManualJournalConflict as exc:
        raise HTTPException(status_code=409, detail="手工台账版本冲突，请刷新后核对") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="手工台账观察时间或内容无效") from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="手工台账版本冲突，请刷新后核对") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="手工台账数据库暂不可用") from exc


@app.post("/workbench/manual-journal/operation", tags=["workbench"], status_code=201)
async def workbench_manual_journal_operation(
    request: Request,
    journal_token: str | None = Header(default=None, alias="X-Workbench-Journal-Token"),
) -> dict[str, object]:
    _manual_journal_access(request, journal_token)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_MANUAL_JOURNAL_BYTES:
            raise HTTPException(status_code=413, detail="手工台账记录过大")
        chunks.append(chunk)
    try:
        payload = ManualOperationApply.model_validate(json.loads(b"".join(chunks)))
    except (ValidationError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="手工台账操作字段无效") from exc
    try:
        engine = build_engine()
        try:
            with Session(engine) as session:
                result = apply_manual_operation(session, payload)
                session.commit()
                return result
        finally:
            engine.dispose()
    except ManualJournalConflict as exc:
        raise HTTPException(status_code=409, detail="手工台账版本冲突，请刷新后核对") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="手工台账操作与现有持仓不一致") from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="手工台账版本冲突，请刷新后核对") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="手工台账数据库暂不可用") from exc


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
