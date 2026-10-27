import time

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.api_key import verify_api_key
from app.config import AppConfig
from app.decision import DecisionEngine
from app.models.decision import DecisionRequest, DecisionResponse

router = APIRouter(
    prefix="/api/v1/decision",
    tags=["의사결정"],
    dependencies=[Depends(verify_api_key)],
)


def get_decision_engine(request: Request) -> DecisionEngine:
    """app.state에서 Lifespan 관리되는 DecisionEngine을 주입합니다."""
    engine = getattr(request.app.state, "decision_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="의사결정 엔진이 초기화되지 않았습니다.",
        )
    return engine


@router.post("", response_model=DecisionResponse)
async def make_decision(
    request: DecisionRequest,
    engine: DecisionEngine = Depends(get_decision_engine),
):
    """비생성형 의사결정 모델을 통해 텍스트 상태(Context)와 질문(Question)으로부터
    최적의 선택(Choice)과 확률 분포를 초고속(Single Forward Pass)으로 결정합니다.
    """
    start_time = time.time()

    # 모델 변경 요청 시 리로드
    if request.model_name and request.model_name != engine.model_name_or_path:
        try:
            engine.initialize(model_name=request.model_name)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"의사결정 모델 '{request.model_name}' 로드 실패: {str(e)}",
            )

    try:
        # 가속 의사결정 실행
        result = engine.decide(
            context=request.context,
            question=request.question,
            decision_type=request.type,
            options=request.options,
            **(request.parameters or {}),
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        config = AppConfig.load()
        include_raw = config.DECISION_INCLUDE_RAW.lower() == "true"

        return DecisionResponse(
            decision=result.decision,
            confidence=result.confidence,
            probabilities=result.probabilities,
            question=request.question,
            type=request.type,
            elapsed_ms=elapsed_ms,
            device=engine.device_name,
            raw=result.raw if include_raw else None,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"의사결정 실행 실패: {str(e)}",
        )


@router.get("/device")
async def get_device_status(
    engine: DecisionEngine = Depends(get_decision_engine),
):
    """현재 가속 디바이스 및 하드웨어 자원 사용 현황을 확인합니다."""
    return {
        "status": "ok",
        "device_info": engine.get_device_info(),
    }


@router.post("/clear-cache")
async def clear_gpu_cache(
    engine: DecisionEngine = Depends(get_decision_engine),
):
    """GPU/가속기 캐시를 비웁니다."""
    engine.clear_cache()
    return {
        "status": "success",
        "message": "GPU 캐시가 정리되었습니다.",
        "device_info": engine.get_device_info(),
    }
