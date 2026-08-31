from pydantic import BaseModel, Field
from typing import Optional, List


class AssessmentRequest(BaseModel):
    """위험성 평가 요청 스키마"""
    domain: str = Field(description="도메인 ID (예: SECURITY)")
    subject: str = Field(description="평가 주제 (예: FastAPI 서버 탈취)")


class RiskItemResponse(BaseModel):
    """위험 항목 개별 응답 스키마"""
    seq: int = Field(description="항목 순번")
    threat_name: str = Field(description="위험 항목명")
    category: str = Field(description="위험 분류")
    risk_level: str = Field(description="위험도 (상/중/하)")
    likelihood: str = Field(description="발생 가능성 (높음/중간/낮음)")
    impact: str = Field(description="영향도 (높음/중간/낮음)")
    risk_score: int = Field(description="위험 점수 (1~9)")
    description: str = Field(description="상세 설명")
    mitigation: str = Field(description="대응방안")
    legal_basis: str = Field(description="관련 법규 조항")


class AssessmentResponse(BaseModel):
    """위험성 평가 결과 응답 스키마"""
    rule_no: str = Field(description="평가 요청 고유 식별자")
    domain_id: str = Field(description="도메인 ID")
    subject: str = Field(description="평가 주제")
    status: str = Field(description="처리 상태 (PENDING/PROCESSING/COMPLETED/FAILED)")
    total_threats: int = Field(default=0, description="도출된 위험 항목 수")
    model_name: Optional[str] = Field(default=None, description="사용된 LLM 모델명")
    prompt_tokens: Optional[int] = Field(default=None, description="입력 토큰 수")
    completion_tokens: Optional[int] = Field(default=None, description="출력 토큰 수")
    elapsed_ms: Optional[int] = Field(default=None, description="처리 소요 시간 (ms)")
    created_at: Optional[str] = None
    results: List[RiskItemResponse] = Field(default=[], description="위험 항목 목록")
