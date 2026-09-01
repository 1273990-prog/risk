import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn

from app.config import AppConfig
from app.common.logger import setup_logger, get_logger
from app.routers import domains, assessments, admin, health

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서비스 시작 시 로거를 초기화하고 설정 정보를 출력합니다."""
    config = AppConfig.load()
    setup_logger(
        log_level=config.LOG_LEVEL,
        log_file_enabled=config.LOG_FILE_ENABLED,
        log_dir=config.LOG_DIR,
    )
    logger.info("Risk Assessment Service 가동")
    logger.info(f"[설정] LLM: {config.LLM_BASE_URL} / Model: {config.LLM_MODEL}")
    logger.info(f"[설정] DB: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    logger.info(f"[설정] LOG_LEVEL={config.LOG_LEVEL}, LOG_FILE_ENABLED={config.LOG_FILE_ENABLED}")
    yield


# FastAPI 앱 생성
app = FastAPI(
    title="Risk Assessment Service",
    description="Gemma 4 기반 위험성 평가 API 서비스",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """모든 HTTP 요청/응답을 자동으로 로깅합니다."""
    request_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        f"→ [{request_id}] {request.method} {request.url.path} from {client_ip}"
    )

    start = time.time()
    response = await call_next(request)
    elapsed_ms = int((time.time() - start) * 1000)

    log_fn = logger.warning if response.status_code >= 400 else logger.info
    log_fn(
        f"← [{request_id}] {response.status_code} {request.method} {request.url.path} "
        f"({elapsed_ms}ms)"
    )

    return response


# 라우터 등록
app.include_router(health.router)
app.include_router(domains.router)
app.include_router(assessments.router)
app.include_router(admin.router)


if __name__ == "__main__":
    config = AppConfig.load()
    uvicorn.run(
        "app.main:app",
        host=config.API_SERVER_HOST,
        port=int(config.API_SERVER_PORT),
        reload=True,
    )
