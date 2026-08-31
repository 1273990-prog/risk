from datetime import datetime
from typing import Dict, Any
import os
import uuid
import hashlib
import secrets

from app.common.constants import RiskConstants


class RiskUtils:
    """위험성 평가 시스템 유틸리티 함수 모음.
    기존 AgentUtils 패턴을 그대로 따릅니다.
    """

    @staticmethod
    def get_rule_no() -> str:
        """고유 식별자(PK) 생성.
        형식: YYYYMMDDHH24MISSMS + 타입코드(00) + UUID4 (하이픈 제거)
        """
        rule_type = "00"

        # 1. YYYYMMDDHH24MISSMS 형태의 현재 시간 포맷팅 (밀리초 3자리 포함)
        now = datetime.now()
        time_str = now.strftime("%Y%m%d%H%M%S%f")[:-3]

        # 2. UUID 생성 후 하이픈('-') 제거
        uuid_str = str(uuid.uuid4()).replace("-", "")

        # 3. 시간 + 타입코드 + UUID 결합
        rule_no = time_str + rule_type + uuid_str

        return rule_no

    @staticmethod
    def generate_api_key() -> str:
        """API Key 원본 생성. 형식: sk- + 32자리 랜덤 hex"""
        return "sk-" + secrets.token_hex(16)

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """API Key를 SHA256으로 해싱합니다. DB 조회용 단방향 해시."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def verify_api_key(api_key: str, stored_hash: str) -> bool:
        """제공된 API Key가 저장된 해시와 일치하는지 검증합니다."""
        return hashlib.sha256(api_key.encode()).hexdigest() == stored_hash

    @staticmethod
    def calculate_risk_score(likelihood: str, impact: str) -> int:
        """발생가능성 × 영향도 매트릭스로 위험 점수를 산출합니다."""
        return RiskConstants.RISK_SCORE_MATRIX.get((likelihood, impact), 0)

    @staticmethod
    def determine_risk_level(score: int) -> str:
        """위험 점수로 위험도 등급을 결정합니다.
        7~9: 상, 4~6: 중, 1~3: 하
        """
        if score >= 7:
            return RiskConstants.HIGH
        elif score >= 4:
            return RiskConstants.MEDIUM
        else:
            return RiskConstants.LOW
