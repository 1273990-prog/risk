import json
import time
from collections import deque
from threading import Lock
from fastapi import Request, HTTPException

from app.common.db_conn import DbConn
from app.common.logger import get_logger
from app.common.utils import RiskUtils
from app.config import AppConfig

logger = get_logger(__name__)

# 분당 호출 한도 슬라이딩 윈도우 (키별 타임스탬프, 인메모리)
# NOTE: 멀티 워커(uvicorn --workers N) 환경에서는 워커별 독립 카운트라
# 엄밀한 전역 한도가 필요하면 DB/Redis 기반 윈도우로 교체해야 합니다.
_WINDOW_SECONDS = 60.0
_hits: dict = {}
_hits_lock = Lock()


def _check_rate_limit(key_id: str, limit: int) -> None:
    """슬라이딩 윈도우 한도 검사. 초과 시 429를 올립니다."""
    now = time.monotonic()
    with _hits_lock:
        dq = _hits.setdefault(key_id, deque())
        while dq and now - dq[0] >= _WINDOW_SECONDS:
            dq.popleft()
        if len(dq) >= limit:
            retry_after = int(_WINDOW_SECONDS - (now - dq[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"분당 호출 한도({limit}회)를 초과했습니다",
                headers={"Retry-After": str(retry_after)},
            )
        dq.append(now)


async def verify_api_key(request: Request) -> dict:
    """FastAPI 의존성: API Key 인증 검증.
    요청 헤더의 X-API-Key를 검증하고 사용량을 갱신합니다.

    Args:
        request: FastAPI Request 객체

    Returns:
        인증된 API Key 정보 딕셔너리 (rule_no, client_name, rate_limit)

    Raises:
        HTTPException: 401 (키 누락 또는 유효하지 않은 키), 429 (분당 한도 초과)
    """
    # ① 헤더에서 API Key 추출
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="API 키가 필요합니다")

    # ② SHA256 해시로 DB 조회
    api_key_hash = RiskUtils.hash_api_key(api_key)

    config = AppConfig.load()
    net_value = config.get_db_net_value("SELECT")
    net_value_json = json.dumps(net_value)

    try:
        db_conn = DbConn(net_value_json)
        query_data = json.dumps({
            "query_key": "SELECT_API_KEY_BY_HASH",
            "params": {"api_key_hash": api_key_hash},
        })
        db_conn.create_request(query_data)
        result = db_conn.create_response()

        key_list = json.loads(result)

        # ③ 유효성 검증
        if not key_list or not key_list[0]:
            raise HTTPException(status_code=401, detail="유효하지 않은 API 키입니다")

        key_info = key_list[0]

        # ④ 분당 호출 한도 검사 (키별 값 우선, 없으면 전역 기본값, 0 이하면 무제한)
        try:
            limit = int(key_info.get("rate_limit") or config.RATE_LIMIT_PER_MINUTE)
        except (TypeError, ValueError):
            limit = 30
        if limit > 0:
            _check_rate_limit(str(key_info["rule_no"]), limit)

        # ⑤ 사용량 갱신 (한도 통과분만 집계)
        update_net_value = config.get_db_net_value("UPDATE")
        update_conn = DbConn(json.dumps(update_net_value))
        update_data = json.dumps({
            "query_key": "UPDATE_API_KEY_USAGE",
            "params": {"rule_no": key_info["rule_no"]},
        })
        update_conn.create_request(update_data)
        update_conn.create_response()

        return key_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[인증] API Key 인증 처리 실패: {e}")
        raise HTTPException(status_code=500, detail="인증 처리 중 오류가 발생했습니다")


async def verify_admin_key(request: Request) -> str:
    """FastAPI 의존성: 관리자 전용 시크릿 키 인증 검증.
    요청 헤더의 X-Admin-Key를 환경변수 ADMIN_SECRET_KEY와 비교합니다.

    Args:
        request: FastAPI Request 객체

    Returns:
        인증된 Admin Key 문자열

    Raises:
        HTTPException: 401 (키 누락), 403 (키 불일치), 500 (서버 미설정)
    """
    import secrets

    admin_key = request.headers.get("X-Admin-Key")
    if not admin_key:
        raise HTTPException(
            status_code=401,
            detail="관리자 인증 키가 필요합니다 (헤더: X-Admin-Key)",
        )

    config = AppConfig.load()
    if not config.ADMIN_SECRET_KEY:
        logger.error("[인증] 서버 환경변수에 ADMIN_SECRET_KEY가 설정되지 않았습니다.")
        raise HTTPException(
            status_code=500,
            detail="서버 관리자 인증 설정이 완료되지 않았습니다",
        )

    if not secrets.compare_digest(admin_key, config.ADMIN_SECRET_KEY):
        raise HTTPException(status_code=403, detail="유효하지 않은 관리자 인증 키입니다")

    return admin_key

