from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseLLMClient(ABC):
    """LLM 클라이언트 추상 기반 클래스.
    모든 LLM 제공자(LM Studio/Gemma, OpenAI 등)는 이 인터페이스를 구현합니다.
    기존 BaseEmbeddingClient 패턴을 따릅니다.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """사용 중인 모델명을 반환합니다."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """LLM 서버 URL을 반환합니다."""
        pass

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> Dict[str, Any]:
        """LLM에 채팅 요청을 보내고 응답을 반환합니다.

        Args:
            system_prompt: 시스템 프롬프트 (역할, 지시사항)
            user_prompt: 사용자 입력 (평가 주제)
            temperature: 추론 온도 (낮을수록 정밀, 높을수록 창의적)

        Returns:
            dict: {
                "content": str (응답 텍스트),
                "model": str (사용된 모델명),
                "prompt_tokens": int (입력 토큰 수),
                "completion_tokens": int (출력 토큰 수)
            }
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """LLM 서버 접속 가능 여부를 확인합니다."""
        pass
