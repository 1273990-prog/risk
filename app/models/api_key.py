from pydantic import BaseModel, Field
from typing import Optional


class ApiKeyCreateRequest(BaseModel):
    """API Key 발급 요청 스키마"""
    client_name: str = Field(description="발급 대상 이름 (예: A사 보안팀)")
    rate_limit: int = Field(default=30, description="분당 최대 호출 수")
    expires_days: Optional[int] = Field(default=None, description="만료일 (일 수, None이면 무기한)")


class ApiKeyCreateResponse(BaseModel):
    """API Key 발급 응답 스키마 (원본 키는 이 응답에서만 1회 표시)"""
    api_key: str = Field(description="API Key 원본 (발급 시 1회만 표시)")
    client_name: str
    message: str = "이 키는 다시 조회할 수 없습니다. 안전하게 보관하세요."


class ApiKeyInfoResponse(BaseModel):
    """API Key 정보 조회 응답 스키마 (원본 키 미포함)"""
    rule_no: str
    api_key_prefix: str = Field(description="키 앞 8자리 (식별용)")
    client_name: str
    is_active: bool
    rate_limit: int
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    total_requests: int
    created_at: Optional[str] = None
