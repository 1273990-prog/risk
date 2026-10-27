"""
의사결정(Decision Engine) 패키지.
팩토리 함수를 통해 엔진 제공자(provider)를 교체할 수 있는 추상화 계층을 제공합니다.
기존 app/llm 패키지 패턴을 그대로 따릅니다.

사용 예:
    from app.decision import create_decision_engine
    engine = create_decision_engine(provider="laya")
    engine.initialize()
    result = engine.decide(context="...", question="...", type="choice", options=[...])
"""
from typing import Any, Dict, Type

from app.decision.base_engine import BaseDecisionEngine, DecisionEngine, DecisionResult
from app.decision.laya_engine import LayaDecisionEngine

# 엔진 제공자명 → 엔진 클래스 매핑 (확장 시 여기에 추가)
_ENGINE_REGISTRY: Dict[str, Type[BaseDecisionEngine]] = {
    "laya": LayaDecisionEngine,
}


def register_decision_engine(provider: str, engine_class: Type[BaseDecisionEngine]) -> None:
    """새로운 의사결정 엔진 클래스를 레지스트리에 동적으로 등록합니다."""
    _ENGINE_REGISTRY[provider.lower()] = engine_class


def create_decision_engine(provider: str = "laya", **kwargs: Any) -> BaseDecisionEngine:
    """의사결정 엔진 팩토리 함수.
    provider 문자열만 바꾸면 소비자 코드 변경 없이 의사결정 엔진을 교체할 수 있습니다.

    Args:
        provider: 의사결정 엔진 제공자 이름 (예: "laya")
        **kwargs: 엔진별 초기화 인자

    Returns:
        BaseDecisionEngine 구현체 인스턴스

    Raises:
        ValueError: 지원하지 않는 provider를 지정한 경우
    """
    engine_class = _ENGINE_REGISTRY.get(provider.lower())
    if engine_class is None:
        supported = ", ".join(_ENGINE_REGISTRY.keys())
        raise ValueError(
            f"[오류] 지원하지 않는 의사결정 엔진입니다: '{provider}'. "
            f"지원 목록: {supported}"
        )
    return engine_class(**kwargs)


__all__ = [
    "BaseDecisionEngine",
    "DecisionEngine",
    "DecisionResult",
    "LayaDecisionEngine",
    "create_decision_engine",
    "register_decision_engine",
]
