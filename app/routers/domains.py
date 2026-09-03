import json
from fastapi import APIRouter, Depends, HTTPException

from app.auth.api_key import verify_api_key
from app.config import AppConfig
from app.engine.risk_engine import RiskEngine
from app.models.domain import DomainCreateRequest, DomainConfigResponse, DomainUpdateRequest
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
        example_subjects=request.example_subjects,
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


@router.patch("/{domain_id}", response_model=DomainConfigResponse)
async def update_domain(
    domain_id: str,
    request: DomainUpdateRequest,
    key_info: dict = Depends(verify_api_key),
):
    """도메인 설정을 수정합니다.
    미지정 필드는 기존값 유지, 수정 후 재검토가 필요해 is_reviewed=false로 돌아갑니다.
    """
    config = AppConfig.load()

    sel_conn = DbConn(json.dumps(config.get_db_net_value("SELECT")))
    sel_conn.create_request(json.dumps({
        "query_key": "SELECT_DOMAIN_CONFIG_BY_ID",
        "params": {"domain_id": domain_id},
    }))
    rows = json.loads(sel_conn.create_response())

    if not rows or not rows[0]:
        raise HTTPException(status_code=404, detail=f"도메인 '{domain_id}'을 찾을 수 없습니다")

    current = rows[0]
    merged = {
        "standards": request.standards if request.standards is not None else current.get("standards"),
        "legal_references": request.legal_references if request.legal_references is not None else current.get("legal_references"),
        "risk_categories": request.risk_categories if request.risk_categories is not None else current.get("risk_categories"),
        "output_instruction": request.output_instruction if request.output_instruction is not None else current.get("output_instruction"),
        "example_subjects": request.example_subjects if request.example_subjects is not None else current.get("example_subjects"),
        "temperature": float(request.temperature) if request.temperature is not None else current.get("temperature"),
        "is_reviewed": False,
        "domain_id": domain_id,
    }

    upd_conn = DbConn(json.dumps(config.get_db_net_value("UPDATE")))
    upd_conn.create_request(json.dumps({
        "query_key": "UPDATE_DOMAIN_CONFIG",
        "params": merged,
    }))
    upd_result = json.loads(upd_conn.create_response())

    if not upd_result or upd_result.get("affected_rows", 0) == 0:
        raise HTTPException(status_code=404, detail=f"도메인 '{domain_id}'을 찾을 수 없습니다")

    sel_conn2 = DbConn(json.dumps(config.get_db_net_value("SELECT")))
    sel_conn2.create_request(json.dumps({
        "query_key": "SELECT_DOMAIN_CONFIG_BY_ID",
        "params": {"domain_id": domain_id},
    }))
    updated = json.loads(sel_conn2.create_response())

    if not updated or not updated[0]:
        raise HTTPException(status_code=404, detail=f"도메인 '{domain_id}'을 찾을 수 없습니다")

    return DomainConfigResponse(**updated[0])


@router.patch("/{domain_id}/approve", response_model=DomainConfigResponse)
async def approve_domain(
    domain_id: str,
    key_info: dict = Depends(verify_api_key),
):
    """도메인을 검토 완료 처리하여 활성화합니다.
    is_reviewed = true로 변경 후 갱신된 행을 반환합니다.
    """
    config = AppConfig.load()
    net_value = config.get_db_net_value("UPDATE")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "ACTIVATE_DOMAIN_CONFIG",
        "params": {"domain_id": domain_id},
    })
    db_conn.create_request(query_data)
    update_result = json.loads(db_conn.create_response())

    if not update_result or update_result.get("affected_rows", 0) == 0:
        raise HTTPException(status_code=404, detail=f"도메인 '{domain_id}'을 찾을 수 없습니다")

    sel_conn = DbConn(json.dumps(config.get_db_net_value("SELECT")))
    sel_conn.create_request(json.dumps({
        "query_key": "SELECT_DOMAIN_CONFIG_BY_ID",
        "params": {"domain_id": domain_id},
    }))
    rows = json.loads(sel_conn.create_response())

    if not rows or not rows[0]:
        raise HTTPException(status_code=404, detail=f"도메인 '{domain_id}'을 찾을 수 없습니다")

    return DomainConfigResponse(**rows[0])
