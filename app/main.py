from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

from app.config import AppConfig
from app.routers import domains, assessments, admin, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서비스 시작 시 설정 정보를 출력합니다."""
    config = AppConfig.load()
    print("[시작] Risk Assessment Service 가동")
    print(f"[설정] LLM: {config.LLM_BASE_URL} / Model: {config.LLM_MODEL}")
    print(f"[설정] DB: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    yield


# FastAPI 앱 생성
app = FastAPI(
    title="Risk Assessment Service",
    description="Gemma 4 기반 위험성 평가 API 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

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
