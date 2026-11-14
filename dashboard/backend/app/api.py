"""The HTTP API. Read-only: every route is a GET."""


import json
import logging
import threading
import time as _time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from . import hktypes as hk
from . import service, units
from .agent_tools import HealthTools
from .catalog import Catalog, load_catalog
from .coach import Coach
from .local_coach import LocalCoach
from .config import Settings, load_settings
from .sources import MemorySource, PostgresSource, Source

log = logging.getLogger(__name__)

# The built web page (`npm run build`). When it exists the API serves it too, so the Mac app
# needs only this one process instead of the API plus the Vite dev server.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

MAX_RANGE_DAYS = 3 * 366
EARLIEST = date(2000, 1, 1)
CACHE_TTL_S = 60.0
# These two read the whole table (~1 s each) and change slowly, so keep them longer.
SLOW_TTL_S = 300.0


class TTLCache:
    """Tiny in-process cache so flipping between tabs doesn't re-query the database."""

    def __init__(self, ttl: float = CACHE_TTL_S, max_items: int = 256):
        self.ttl, self.max_items = ttl, max_items
        self._d: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: tuple, fn: Callable[[], Any], ttl: float | None = None) -> Any:
        now = _time.monotonic()
        with self._lock:
            hit = self._d.get(key)
            if hit and now - hit[0] < (self.ttl if ttl is None else ttl):
                return hit[1]
        value = fn()
        with self._lock:
            if len(self._d) >= self.max_items:
                self._d.clear()
            self._d[key] = (now, value)
        return value


def _is_db_unavailable(exc: Exception) -> bool:
    try:
        import psycopg
        from psycopg_pool import PoolTimeout
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, (psycopg.OperationalError, PoolTimeout))


def build_source(settings: Settings) -> Source:
    if settings.demo:
        from .demo import UNITS, generate

        log.info("DEMO=1: serving synthetic data")
        return MemorySource(
            generate(now=settings.demo_now, tz=settings.tz),
            settings,
            last_upload=(settings.demo_now or datetime.now(timezone.utc)) - timedelta(minutes=7),
            units=UNITS,
        )
    return PostgresSource(settings)


def create_app(
    settings: Settings | None = None, source: Source | None = None, catalog: Catalog | None = None
) -> FastAPI:
    settings = settings or load_settings()
    catalog = catalog or load_catalog(settings.types_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.source = source or build_source(settings)
        tools = HealthTools(settings, app.state.source, catalog)
        app.state.coach = Coach(tools)
        app.state.local_coach = LocalCoach(tools)  # the on-device model, when its server is running
        if not settings.demo:
            # Warm the slow, whole-table queries so the first page load doesn't wait for them.
            threading.Thread(target=warm, args=(app,), daemon=True, name="cache-warm").start()
        try:
            yield
        finally:
            app.state.source.close()

    app = FastAPI(
        title="HealthSync dashboard API",
        description="Read-only API over the Apple Health samples synced by apple-health-sync.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.catalog = catalog
    app.state.cache = TTLCache()

    # Only answer requests addressed to this machine (blocks DNS-rebinding tricks).
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_methods=["GET"],
        allow_headers=[],
        allow_credentials=False,
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        # Never leak connection strings or SQL in an error message.
        if _is_db_unavailable(exc):
            log.warning("database unavailable on %s: %s", request.url.path, type(exc).__name__)
            return JSONResponse(
                {"detail": "Can't reach the database. Check DATABASE_URL in dashboard/.env and your network."},
                status_code=503,
            )
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal error. Check the backend log."}, status_code=500)

    def src(request: Request) -> Source:
        return request.app.state.source

    def cached(request: Request, key: tuple, fn: Callable[[], Any]) -> Any:
        return request.app.state.cache.get_or_set(key, fn)

    SourceDep = Annotated[Source, Depends(src)]

    def date_range(
        from_: Annotated[date | None, Query(alias="from", description="Local date, inclusive")] = None,
        to: Annotated[date | None, Query(description="Local date, inclusive")] = None,
    ) -> tuple[date, date]:
        today = service.today_local(settings.tz, settings.demo_now)
        to = to or today
        from_ = from_ or (to - timedelta(days=29))
        if from_ > to:
            raise HTTPException(422, "'from' must be on or before 'to'")
        if (to - from_).days + 1 > MAX_RANGE_DAYS:
            raise HTTPException(422, f"Date range is limited to {MAX_RANGE_DAYS} days")
        if from_ < EARLIEST or to > today + timedelta(days=1):
            raise HTTPException(422, "Date out of range")
        return from_, to

    RangeDep = Annotated[tuple[date, date], Depends(date_range)]

    def last_upload(cache: TTLCache, source: Source) -> datetime | None:
        return cache.get_or_set(("last_upload",), source.last_upload, ttl=SLOW_TTL_S)

    def warm(app: FastAPI) -> None:
        try:
            last_upload(app.state.cache, app.state.source)
            type_stats_for(app.state.cache, app.state.source)
        except Exception as e:  # noqa: BLE001 - warming is best-effort
            log.info("cache warm-up skipped: %s", type(e).__name__)

    @app.get("/api/health")
    def health(request: Request, source: SourceDep) -> dict[str, Any]:
        reachable = source.ping()
        last_upload_at = None
        if reachable:
            try:
                lu = last_upload(request.app.state.cache, source)
                last_upload_at = lu.isoformat() if lu else None
            except Exception:  # noqa: BLE001
                log.warning("could not read last upload time")
        return {
            "ok": True,
            "demo": settings.demo,
            "database_reachable": reachable,
            "last_upload": last_upload_at,
            "tz": settings.tz_name,
        }

    def type_stats_for(cache: TTLCache, source: Source) -> dict[str, Any]:
        """Types that have data, cached; unknown ones get registered with a best guess."""

        def load() -> dict[str, Any]:
            out = {}
            for st in source.type_stats():
                info = catalog.get(st.type) or catalog.add_discovered(st.type, st.unit)
                out[st.type] = (info, st)
            return out

        today = service.today_local(settings.tz, settings.demo_now)
        return cache.get_or_set(("type_stats", today), load, ttl=SLOW_TTL_S)

    def type_stats(request: Request, source: Source) -> dict[str, Any]:
        return type_stats_for(request.app.state.cache, source)

    @app.get("/api/types")
    def types(request: Request, source: SourceDep) -> dict[str, Any]:
        """Every type that has data, with its catalog entry, row count and latest date."""
        rows = []
        for info, st in type_stats(request, source).values():
            disp, _ = units.display(info.id, info.unit)
            rows.append(
                {
                    **info.to_dict(),
                    "display_unit": "min" if info.aggregation == "duration" or info.kind != "quantity" else disp,
                    "count": st.count,
                    "latest": st.latest.isoformat() if st.latest else None,
                }
            )
        rows.sort(key=lambda r: (r["group"], r["name"]))
        return {
            "catalog_source": catalog.source,
            "catalog_size": len(catalog.by_id),
            "types": rows,
        }

    @app.get("/api/metric")
    def metric(
        request: Request,
        source: SourceDep,
        rng: RangeDep,
        type: Annotated[str, Query(max_length=128, description="Any HealthKit identifier in the catalog")],
    ) -> dict[str, Any]:
        info = catalog.get(type)
        if info is None:
            hit = type_stats(request, source).get(type)
            info = hit[0] if hit else None
        if info is None:
            raise HTTPException(422, "Unknown type")
        return cached(request, ("metric", info.id, *rng), lambda: service.metric(source, info, *rng, settings.tz))

    @app.get("/api/summary")
    def summary(
        request: Request,
        source: SourceDep,
        days: Annotated[int, Query(ge=1, le=90)] = 7,
    ) -> dict[str, Any]:
        today = service.today_local(settings.tz, settings.demo_now)
        return cached(request, ("summary", days, today), lambda: service.summary(source, days, settings.tz, now=settings.demo_now))

    @app.get("/api/daily")
    def daily(
        request: Request,
        source: SourceDep,
        rng: RangeDep,
        type: Annotated[str, Query(max_length=64, description="e.g. steps, hrv, body_mass")],
    ) -> dict[str, Any]:
        metric = hk.lookup_metric(type)
        if metric is None:
            raise HTTPException(422, f"Unknown type. Allowed: {', '.join(hk.METRICS)}")
        return cached(
            request, ("daily", metric.key, *rng), lambda: service.daily(source, metric, *rng, settings.tz)
        )

    @app.get("/api/sleep")
    def sleep(request: Request, source: SourceDep, rng: RangeDep) -> dict[str, Any]:
        return cached(request, ("sleep", *rng), lambda: service.sleep(source, *rng, settings.tz))

    @app.get("/api/workouts")
    def workouts(request: Request, source: SourceDep, rng: RangeDep) -> dict[str, Any]:
        return cached(request, ("workouts", *rng), lambda: service.workouts(source, *rng, settings.tz))

    @app.get("/api/heart")
    def heart(request: Request, source: SourceDep, rng: RangeDep) -> dict[str, Any]:
        return cached(request, ("heart", *rng), lambda: service.heart(source, *rng, settings.tz))

    @app.get("/api/body")
    def body(request: Request, source: SourceDep, rng: RangeDep) -> dict[str, Any]:
        return cached(request, ("body", *rng), lambda: service.body(source, *rng, settings.tz))

    # ---------------------------------------------------------------- coach (chat)

    class ChatIn(BaseModel):
        message: str = Field(max_length=8000)
        conversation_id: str | None = Field(default=None, max_length=64)
        engine: Literal["claude", "local"] = "claude"

    def same_origin_only(request: Request) -> None:
        """The only POST route spends API credit and can write notes, so refuse anything a
        different website could trigger: it must be JSON, carry our header (which forces a
        CORS preflight that the GET-only CORS policy rejects), and come from this origin."""
        if request.headers.get("x-coach") != "1" or not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(403, "Forbidden")
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
            raise HTTPException(403, "Forbidden")

    @app.get("/api/coach/status")
    def coach_status() -> dict[str, Any]:
        local = LocalCoach.info()
        return {"configured": Coach.configured(),
                "local": {"available": local is not None, "model": local and local.get("base"),
                          "fine_tuned": bool(local and local.get("adapter"))}}

    @app.post("/api/coach/chat")
    async def coach_chat(request: Request) -> StreamingResponse:
        same_origin_only(request)  # before reading the body, so nothing untrusted is parsed
        try:
            body = ChatIn.model_validate_json(await request.body())
        except ValueError:
            raise HTTPException(422, "Expected {message, conversation_id?}") from None
        coach = request.app.state.local_coach if body.engine == "local" else request.app.state.coach
        events = coach.reply(body.conversation_id, body.message)
        sse = (f"data: {json.dumps(e)}\n\n" for e in events)
        return StreamingResponse(sse, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # Mounted last so every /api route above takes priority.
    if (FRONTEND_DIST / "index.html").is_file():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app
