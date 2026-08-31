from pydantic import BaseModel, Field
from typing import Optional


class DomainCreateRequest(BaseModel):
    """도메인 생성 요청 스키마"""
    domain_id: str = Field(description="도메인 식별자 (예: SECURITY)")
    domain_name: str = Field(description="도메인 표시명 (예: 보안 전문가)")
    role_description: str = Field(description="전문가 역할 정의 (예: 정보보안 위험성 평가 전문가)")


class DomainConfigResponse(BaseModel):
    """도메인 설정 응답 스키마"""
    rule_no: Optional[str] = None
    domain_id: str
    domain_name: str
    role_description: str
    standards: Optional[str] = Field(default=None, description="판단 기준 표준 (Gemma 생성)")
    legal_references: Optional[str] = Field(default=None, description="관련 법규 (Gemma 생성)")
    risk_categories: Optional[str] = Field(default=None, description="위험 분류 체계 (Gemma 생성)")
    output_instruction: Optional[str] = None
    temperature: float = 0.3
    is_active: bool = True
    is_reviewed: bool = Field(default=False, description="관리자 검토 완료 여부")
    created_at: Optional[str] = None
