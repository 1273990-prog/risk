import time
from typing import Dict, Any, Optional

from openai import OpenAI

from app.llm.base_client import BaseLLMClient


class GemmaClient(BaseLLMClient):
    """LM Studio + Gemma 4 기반 LLM 클라이언트.
    OpenAI 호환 API를 사용하여 LM Studio 서버와 통신합니다.
    기존 GeminiEmbeddingClient의 재시도 로직 패턴을 따릅니다.
    """

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2  # 일반 오류 재시도 대기시간(초)

    def __init__(self, base_url: str = "http://localhost:1234/v1", model: str = "gemma-4"):
        """Gemma 클라이언트를 초기화합니다.

        Args:
            base_url: LM Studio 서버 URL (기본값: http://localhost:1234/v1)
            model: 사용할 모델명 (기본값: gemma-4)
        """
        self._base_url = base_url
        self._model = model

        # LM Studio는 실제 API Key가 불필요하므로 더미값 사용
        self._client = OpenAI(
            base_url=base_url,
            api_key="lm-studio",
        )

        print(f"  [Gemma 초기화] 서버: {base_url}")
        print(f"  [Gemma 초기화] 모델: {model}")

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> Dict[str, Any]:
        """LM Studio를 통해 Gemma 4에 채팅 요청을 보냅니다.
        재시도 로직이 포함되어 있습니다.
        """
        return self._chat_with_retry(system_prompt, user_prompt, temperature)

    def health_check(self) -> bool:
        """LM Studio 서버 접속 가능 여부를 확인합니다."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def _chat_with_retry(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> Dict[str, Any]:
        """재시도 로직이 포함된 채팅 요청. GeminiEmbeddingClient._embed_with_retry 패턴."""
        last_exception: Optional[Exception] = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )

                # 응답 파싱
                choice = response.choices[0]
                usage = response.usage

                return {
                    "content": choice.message.content,
                    "model": response.model,
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                }

            except Exception as e:
                last_exception = e
                delay = self._RETRY_BASE_DELAY * attempt
                print(
                    f"  [재시도] LLM 오류 발생 (시도 {attempt}/{self._MAX_RETRIES}), "
                    f"{delay}초 대기 후 재시도... (원인: {e})"
                )
                time.sleep(delay)

        if last_exception:
            print(f"  [오류] LLM 호출 실패: {last_exception}")
            raise last_exception
