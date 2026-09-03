import json
from fastapi import APIRouter, Depends, Query

from app.auth.api_key import verify_api_key
from app.config import AppConfig
from app.engine.risk_engine import RiskEngine
from app.models.assessment import AssessmentRequest, AssessmentResponse, RiskItemResponse, RiskRequestResponse
from app.common.db_conn import DbConn
from app.common.constants import RiskConstants

router = APIRouter(prefix="/api/v1/risk", tags=["위험성 평가"])


@router.post("/evaluate", response_model=AssessmentResponse)
async def evaluate(
    request: AssessmentRequest,
    key_info: dict = Depends(verify_api_key),
):
    """위험성 평가를 실행합니다.
    도메인과 주제를 지정하면 Gemma가 위험 항목 목록을 생성합니다.
    """
    config = AppConfig.load()
    engine = RiskEngine(config)

    result = engine.evaluate(
        domain_id=request.domain,
        subject=request.subject,
        request_type=RiskConstants.REALTIME,
    )

    # 결과를 응답 모델에 맞게 변환
    risk_items = [
        RiskItemResponse(
            seq=idx + 1,
            threat_name=item.get("threat_name", ""),
            category=item.get("category", ""),
            risk_level=item.get("risk_level", ""),
            likelihood=item.get("likelihood", ""),
            impact=item.get("impact", ""),
            risk_score=item.get("risk_score", 0),
            description=item.get("description", ""),
            mitigation=item.get("mitigation", ""),
            legal_basis=item.get("legal_basis", ""),
        )
        for idx, item in enumerate(result.get("results", []))
    ]

    return AssessmentResponse(
        rule_no=result["rule_no"],
        domain_id=result["domain_id"],
        subject=result["subject"],
        status=result["status"],
        total_threats=result["total_threats"],
        model_name=result.get("model_name"),
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
        elapsed_ms=result.get("elapsed_ms"),
        created_at=result.get("created_at"),
        completed_at=result.get("completed_at"),
        results=risk_items,
    )


@router.get("/results", response_model=list[RiskRequestResponse])
async def list_results(
    limit: int = Query(default=20, ge=1, le=100, description="조회 건수"),
    offset: int = Query(default=0, ge=0, description="시작 위치"),
    key_info: dict = Depends(verify_api_key),
):
    """평가 요청 목록을 조회합니다."""
    config = AppConfig.load()
    net_value = config.get_db_net_value("SELECT")

    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "SELECT_RISK_REQUESTS",
        "params": {"limit": limit, "offset": offset},
    })
    db_conn.create_request(query_data)
    result = json.loads(db_conn.create_response())

    if not result or not result[0]:
        return []

    return [RiskRequestResponse(**row) for row in result]


@router.get("/results/{request_id}", response_model=AssessmentResponse)
async def get_result(
    request_id: str,
    key_info: dict = Depends(verify_api_key),
):
    """평가 결과 상세를 조회합니다. (요청 정보 + 위험 항목 목록)"""
    config = AppConfig.load()
    net_value = config.get_db_net_value("SELECT")

    # 평가 요청 조회
    db_conn = DbConn(json.dumps(net_value))
    query_data = json.dumps({
        "query_key": "SELECT_RISK_REQUEST_BY_ID",
        "params": {"rule_no": request_id},
    })
    db_conn.create_request(query_data)
    request_result = json.loads(db_conn.create_response())

    if not request_result or not request_result[0]:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="평가 결과를 찾을 수 없습니다")

    req_data = request_result[0]

    # 위험 항목 조회
    db_conn2 = DbConn(json.dumps(net_value))
    query_data2 = json.dumps({
        "query_key": "SELECT_RISK_RESULTS_BY_REQUEST",
        "params": {"group_no": request_id},
    })
    db_conn2.create_request(query_data2)
    items_result = json.loads(db_conn2.create_response())

    # 응답 조립
    risk_items = []
    if items_result and items_result[0]:
        risk_items = [RiskItemResponse(**item) for item in items_result]

    return AssessmentResponse(
        rule_no=req_data["rule_no"],
        domain_id=req_data["domain_id"],
        subject=req_data["subject"],
        status=req_data["status"],
        total_threats=req_data.get("total_threats", 0),
        model_name=req_data.get("model_name"),
        prompt_tokens=req_data.get("prompt_tokens"),
        completion_tokens=req_data.get("completion_tokens"),
        elapsed_ms=req_data.get("elapsed_ms"),
        created_at=str(req_data.get("created_at", "")),
        completed_at=str(req_data.get("completed_at", "")),
        results=risk_items,
    )
