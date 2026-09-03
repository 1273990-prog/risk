"""
LLM 클라이언트 패키지.
팩토리 함수를 통해 제공자(provider)를 교체할 수 있는 추상화 계층을 제공합니다.
기존 embedding/__init__.py 패턴을 그대로 따릅니다.

사용 예:
    from app.llm import create_llm_client
    client = create_llm_client(provider="lmstudio", base_url="http://localhost:1234/v1")
    result = client.chat(system_prompt="...", user_prompt="FastAPI 서버 탈취")

    client = create_llm_client(
        provider="opencode",
        model="muse-spark-1.3-contributor-free",
        api_key="...",
    )
"""
from app.llm.base_client import BaseLLMClient
from app.llm.lmstudio_client import LmStudioClient
from app.llm.opencode_client import OpenCodeClient

# 제공자명 → 클라이언트 클래스 매핑 (확장 시 여기에 추가)
_PROVIDER_REGISTRY = {
    "lmstudio": LmStudioClient,
    "opencode": OpenCodeClient,
}


def create_llm_client(provider: str = "lmstudio", **kwargs) -> BaseLLMClient:
    """LLM 클라이언트 팩토리 함수.
    provider 문자열만 바꾸면 소비자 코드 변경 없이 LLM을 교체할 수 있습니다.

    Args:
        provider: LLM 제공자 이름 ("lmstudio", "opencode")
        **kwargs: 제공자별 초기화 인자 (예: base_url, model, api_key)

    Returns:
        BaseLLMClient 구현체 인스턴스

    Raises:
        ValueError: 지원하지 않는 provider를 지정한 경우
    """
    client_class = _PROVIDER_REGISTRY.get(provider.lower())
    if client_class is None:
        supported = ", ".join(_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"[오류] 지원하지 않는 LLM 제공자입니다: '{provider}'. "
            f"지원 목록: {supported}"
        )
    return client_class(**kwargs)


__all__ = [
    "BaseLLMClient",
    "LmStudioClient",
    "OpenCodeClient",
    "create_llm_client",
]
