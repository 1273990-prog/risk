import json
from fastapi import APIRouter

from app.config import AppConfig
from app.llm import create_llm_client
from app.common.db_conn import DbConn

router = APIRouter(prefix="/api/v1", tags=["상태 확인"])


@router.get("/health")
async def health_check():
    """서비스 상태를 확인합니다. LLM 서버 및 DB 접속 가능 여부를 반환합니다."""
    config = AppConfig.load()

    # LLM 상태 확인
    llm_ok = False
    try:
        client = create_llm_client(
            provider="gemma",
            base_url=config.LLM_BASE_URL,
            model=config.LLM_MODEL,
        )
        llm_ok = client.health_check()
    except Exception:
        llm_ok = False

    # DB 상태 확인
    db_ok = False
    try:
        net_value = config.get_db_net_value("SELECT")
        db_conn = DbConn(json.dumps(net_value))
        query_data = json.dumps({
            "query_key": "SELECT_ALL_DOMAIN_CONFIGS",
            "params": {},
        })
        db_conn.create_request(query_data)
        db_conn.create_response()
        db_ok = True
    except Exception:
        db_ok = False

    status = "ok" if (llm_ok and db_ok) else "degraded"

    return {"status": status, "llm": llm_ok, "db": db_ok}
