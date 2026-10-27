from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DecisionResult:
    """의사결정 엔진의 표준 결과 구조체"""

    __slots__ = ("decision", "confidence", "probabilities", "raw")

    def __init__(
        self,
        decision: Optional[str] = None,
        confidence: Optional[float] = None,
        probabilities: Optional[Dict[str, float]] = None,
        raw: Any = None,
    ):
        self.decision = decision
        self.confidence = round(float(confidence), 4) if confidence is not None else None
        self.probabilities = probabilities or {}
        self.raw = raw

    def get(self, key: str, default: Any = None) -> Any:
        """딕셔너리 스타일 조회를 위한 헬퍼 메서드"""
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "probabilities": self.probabilities,
            "raw": self.raw,
        }


class BaseDecisionEngine(ABC):
    """의사결정 엔진 추상 기본 클래스.

    모든 의사결정 엔진(Laya, HuggingFace, vLLM 등)은
    이 인터페이스를 상속받아 구현해야 합니다.
    """

    @abstractmethod
    def initialize(self, model_name: Optional[str] = None, **kwargs: Any) -> None:
        """모델을 가속 디바이스 메모리에 로드하고 추론 준비를 완료합니다.

        Args:
            model_name: 사용할 모델 이름 또는 경로
            **kwargs: 엔진별 추가 파라미터
        """

    @abstractmethod
    def decide(
        self,
        context: str,
        question: str,
        decision_type: str = "choice",
        options: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> DecisionResult:
        """주어진 컨텍스트와 질문으로부터 결정을 도출합니다.

        Args:
            context: 평가 대상 텍스트 상태
            question: 결정할 질문
            decision_type: 결정 유형 (choice, score, noul 등)
            options: 선택지 목록
            **kwargs: 엔진별 추가 파라미터

        Returns:
            DecisionResult: 표준 결정 결과 객체
        """

    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """현재 가속 하드웨어 및 리소스 상태 정보를 반환합니다."""

    @abstractmethod
    def clear_cache(self) -> None:
        """GPU/가속기 메모리 캐시를 정리합니다."""

    @property
    @abstractmethod
    def device_name(self) -> str:
        """현재 연산 디바이스 이름을 반환합니다. (예: 'cuda', 'cpu')"""

    @property
    @abstractmethod
    def model_name_or_path(self) -> str:
        """현재 로드된 모델의 이름 또는 경로를 반환합니다."""


# 편의를 위한 별칭
DecisionEngine = BaseDecisionEngine
