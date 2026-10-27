from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DecisionRequest(BaseModel):
    """의사결정(Decision) 요청 모델"""
    context: str = Field(
        ...,
        description="평가 대상 텍스트 상태(State / Context)",
        example="축하합니다! 당첨금 1,000만 원 수령을 위해 아래 링크를 즉시 클릭하세요.",
    )
    question: str = Field(
        ...,
        description="결정할 질문(Question)",
        example="이 메시지의 카테고리는 무엇인가요?",
    )
    type: str = Field(
        default="choice",
        description="결정 유형 (choice: 다지선다, score: 척도 평가, noul: 참/거짓 확률)",
        example="choice",
    )
    options: Optional[List[str]] = Field(
        default=None,
        description="선택지 목록 (type이 choice일 때 필수)",
        example=["정상 알림", "스팸 광고", "고객 문의"],
    )
    model_name: Optional[str] = Field(
        default=None,
        description="사용할 Laya 모델 체크포인트 (기본: convaiinnovations/laya-multilingual)",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="추가 추론 파라미터",
    )


class DecisionResponse(BaseModel):
    """의사결정(Decision) 응답 모델"""
    decision: Optional[str] = Field(..., description="최종 결정된 항목 (선택된 옵션)")
    confidence: Optional[float] = Field(None, description="결정 신뢰도 (0.0 ~ 1.0)")
    probabilities: Optional[Dict[str, float]] = Field(default_factory=dict, description="선택지별 확률 분포")
    question: str = Field(..., description="입력된 질문")
    type: str = Field(..., description="결정 유형")
    elapsed_ms: float = Field(..., description="GPU 가속 소요 시간(ms)")
    device: str = Field(..., description="연산에 사용된 디바이스")
    raw: Optional[Any] = Field(None, description="Laya 모델 원본 응답")
