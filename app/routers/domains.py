import json
from fastapi import APIRouter, Depends

from app.auth.api_key import verify_api_key
from app.config import AppConfig
from app.engine.risk_engine import RiskEngine
from app.models.domain import DomainCreateRequest, DomainConfigResponse
from app.common.db_conn import DbConn

router = APIRouter(prefix="/api/v1/domains", tags=["도메인 관리"])


@router.post("/", response_model=DomainConfigResponse)
async def create_domain(
    request: DomainCreateRequest,
    key_info: dict = Depends(verify_api_key),
):
    """도메인을 생성합니다.
    Gemma가 standards, legal_references, risk_categories를 자동 생성합니다.
    생성 후 is_reviewed=false 상태이며, 관리자 검토 후 활성화해야 합니다.
    """
    config = AppConfig.load()
    engine = RiskEngine(config)

    result = engine.generate_domain_knowledge(
        domain_id=request.domain_id,
        domain_name=request.domain_name,
        role_description=request.role_description,
    )

    return DomainConfigResponse(**result)


@router.get("/{domain_id}", response_model=DomainConfigResponse)
async def get_domain(
    domain_id: str,
    key_info: dict = Depends(verify_api_key),
):
    """도메인 설정을 조회합니다."""
    config = AppConfig.load()
    net_value = config.get_db_net_value("SELECT")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "SELECT_DOMAIN_CONFIG_BY_ID",
        "params": {"domain_id": domain_id},
    })
    db_conn.create_request(query_data)
    result = json.loads(db_conn.create_response())

    if not result or not result[0]:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"도메인 '{domain_id}'을 찾을 수 없습니다")

    return DomainConfigResponse(**result[0])


@router.patch("/{domain_id}/approve")
async def approve_domain(
    domain_id: str,
    key_info: dict = Depends(verify_api_key),
):
    """도메인을 검토 완료 처리하여 활성화합니다.
    is_reviewed = true로 변경됩니다.
    """
    config = AppConfig.load()
    net_value = config.get_db_net_value("UPDATE")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "ACTIVATE_DOMAIN_CONFIG",
        "params": {"domain_id": domain_id},
    })
    db_conn.create_request(query_data)
    db_conn.create_response()

    return {"message": f"도메인 '{domain_id}' 검토 완료 및 활성화되었습니다"}
