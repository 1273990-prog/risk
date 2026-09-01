import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends

from app.auth.api_key import verify_admin_key
from app.config import AppConfig
from app.common.db_conn import DbConn
from app.common.utils import RiskUtils
from app.models.api_key import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyInfoResponse

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["관리자"],
    dependencies=[Depends(verify_admin_key)],
)


@router.post("/keys", response_model=ApiKeyCreateResponse)
async def create_api_key(request: ApiKeyCreateRequest):
    """API Key를 발급합니다.
    원본 키는 이 응답에서만 1회 표시됩니다. 이후 조회 불가.
    """
    # ① 원본 키 생성
    api_key = RiskUtils.generate_api_key()
    api_key_hash = RiskUtils.hash_api_key(api_key)
    api_key_prefix = api_key[:8] + "**"

    # ② 만료일 계산
    expires_at = None
    if request.expires_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=request.expires_days)).isoformat()

    # ③ DB 저장
    config = AppConfig.load()
    net_value = config.get_db_net_value("INSERT")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "INSERT_API_KEY",
        "params": {
            "rule_no": RiskUtils.get_rule_no(),
            "api_key_hash": api_key_hash,
            "api_key_prefix": api_key_prefix,
            "client_name": request.client_name,
            "is_active": True,
            "rate_limit": request.rate_limit,
            "expires_at": expires_at,
            "last_used_at": None,
            "total_requests": 0,
        },
    })
    db_conn.create_request(query_data)
    db_conn.create_response()

    # ④ 원본 키 반환 (1회만)
    return ApiKeyCreateResponse(
        api_key=api_key,
        client_name=request.client_name,
    )


@router.get("/keys")
async def list_api_keys():
    """발급된 API Key 목록을 조회합니다. (원본 키 미포함)"""
    config = AppConfig.load()
    net_value = config.get_db_net_value("SELECT")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "SELECT_ALL_API_KEYS",
        "params": {},
    })
    db_conn.create_request(query_data)
    result = json.loads(db_conn.create_response())

    return result


@router.delete("/keys/{key_id}")
async def deactivate_api_key(key_id: str):
    """API Key를 비활성화합니다."""
    config = AppConfig.load()
    net_value = config.get_db_net_value("UPDATE")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "DEACTIVATE_API_KEY",
        "params": {"rule_no": key_id},
    })
    db_conn.create_request(query_data)
    db_conn.create_response()

    return {"message": f"API Key '{key_id}' 비활성화 완료"}
