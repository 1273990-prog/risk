import os
import time
from typing import Dict, Any, Optional

from openai import OpenAI

from app.llm.base_client import BaseLLMClient
from app.common.logger import get_logger

logger = get_logger(__name__)


class OpenCodeClient(BaseLLMClient):
    """OpenCode Zen 기반 클라우드 LLM 클라이언트 (기본 모델: Muse Spark free).

    Zen은 모델 계열에 따라 엔드포인트가 다르므로 모델명으로 분기합니다.
    - Responses API (`/v1/responses`): muse-spark, gpt-, grok 계열
    - Chat Completions API (`/v1/chat/completions`): big-pickle, mimo, ling,
      nemotron, deepseek, glm, kimi, minimax 등 OpenAI 호환 계열

    `base_url`은 게이트웨이 루트(`https://opencode.ai/zen/v1`)를 지정합니다.
    OpenAI SDK가 경로(`/responses`, `/chat/completions`)를 붙입니다.
    """

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2  # 일반 오류 재시도 대기시간(초)

    # Responses API를 사용해야 하는 모델 접두사 (Zen 문서 기준)
    _RESPONSES_PREFIXES = ("muse-spark", "gpt-", "grok")

    def __init__(
        self,
        base_url: str = "https://opencode.ai/zen/v1",
        model: str = "muse-spark-1.3-contributor-free",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """OpenCode Zen 클라이언트를 초기화합니다.

        Args:
            base_url: Zen 게이트웨이 URL (기본값: https://opencode.ai/zen/v1)
            model: 사용할 모델명 (기본값: muse-spark-1.3-contributor-free)
            api_key: Zen API 키. 미지정 시 OPENCODE_ZEN_API_KEY → LLM_API_KEY 순 조회
            timeout: 요청 타임아웃(초)

        Raises:
            ValueError: API 키가 없을 경우
        """
        self._base_url = base_url.rstrip("/")
        self._model = model

        resolved_key = (
            api_key
            or os.environ.get("OPENCODE_ZEN_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        ).strip()
        if not resolved_key:
            raise ValueError(
                "[오류] OpenCode Zen API 키가 없습니다. "
                "OPENCODE_ZEN_API_KEY 환경변수를 설정하세요. "
                "(발급: https://opencode.ai/auth)"
            )

        self._client = OpenAI(
            base_url=self._base_url,
            api_key=resolved_key,
            timeout=timeout,
        )

        logger.info(f"[LLM] OpenCode 초기화 - 서버: {self._base_url}, 모델: {model}")

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> Dict[str, Any]:
        """Zen 모델에 채팅 요청을 보냅니다. 모델 계열에 따라 API를 분기합니다."""
        return self._chat_with_retry(system_prompt, user_prompt, temperature)

    def health_check(self) -> bool:
        """Zen 게이트웨이 접속 가능 여부를 확인합니다. (GET /models)"""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def _use_responses_api(self, model: str) -> bool:
        name = model.lower()
        return name.startswith(self._RESPONSES_PREFIXES)

    def _chat_with_retry(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> Dict[str, Any]:
        last_exception: Optional[Exception] = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                if self._use_responses_api(self._model):
                    return self._create_response(system_prompt, user_prompt, temperature)
                return self._create_chat_completion(system_prompt, user_prompt, temperature)

            except Exception as e:
                last_exception = e
                delay = self._RETRY_BASE_DELAY * attempt
                logger.warning(
                    f"[LLM] 호출 오류 (시도 {attempt}/{self._MAX_RETRIES}), "
                    f"{delay}초 대기 후 재시도... (원인: {e})"
                )
                time.sleep(delay)

        if last_exception:
            logger.error(f"[LLM] 최종 호출 실패 ({self._MAX_RETRIES}회 초과): {last_exception}")
            raise last_exception

    def _create_chat_completion(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> Dict[str, Any]:
        """OpenAI 호환 계열 (big-pickle, mimo 등) 요청."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )

        choice = response.choices[0]
        usage = response.usage

        return {
            "content": choice.message.content or "",
            "model": response.model or self._model,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
        }

    def _create_response(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> Dict[str, Any]:
        """Responses API 계열 (muse-spark, gpt, grok) 요청.

        Responses API는 system 대신 developer 역할을 권장하므로 매핑합니다.
        reasoning 모델에서 temperature를 거부하면 온도 없이 1회 재시도합니다.
        """
        input_messages = [
            {"role": "developer", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._client.responses.create(
                model=self._model,
                input=input_messages,
                temperature=temperature,
            )
        except Exception as e:
            msg = str(e).lower()
            if "temperature" in msg:
                logger.warning(f"[LLM] temperature 미지원 모델, 온도 없이 재시도 (원인: {e})")
                response = self._client.responses.create(
                    model=self._model,
                    input=input_messages,
                )
            else:
                raise

        content = getattr(response, "output_text", "") or self._extract_output_text(response)
        usage = getattr(response, "usage", None)

        return {
            "content": content,
            "model": getattr(response, "model", None) or self._model,
            "prompt_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        }

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        """`output_text` 헬퍼가 비어 있을 때 output 배열에서 텍스트를 직접 추출합니다."""
        texts = []
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                text = getattr(part, "text", "")
                if text:
                    texts.append(text)
        return "".join(texts)
