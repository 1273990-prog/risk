from contextlib import nullcontext
from typing import Any, Dict, List, Optional

import torch
import laya

from app.common.logger import get_logger
from app.decision.base_engine import BaseDecisionEngine, DecisionResult

logger = get_logger(__name__)


# ==============================================================================
# GPU 가속 및 최적화 유틸리티 (CUDA / Apple Silicon MPS / CPU)
# ==============================================================================

def get_optimal_device() -> torch.device:
    """CUDA 또는 Apple Silicon MPS 가용성을 확인하고 최적의 가속 디바이스를 반환합니다."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"[GPU 가속] CUDA 디바이스 감지: {torch.cuda.get_device_name(0)}")
        return device
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("[GPU 가속] Apple Silicon MPS 가속 디바이스 감지")
        return device
    else:
        logger.warning("[GPU 가속 불가] 사용 가능한 GPU가 없어 CPU로 구동됩니다.")
        return torch.device("cpu")


def configure_gpu_acceleration(device: torch.device):
    """초고속 결정을 위한 PyTorch GPU 하드웨어 가속 플래그를 설정합니다."""
    if device.type == "cuda":
        # 1. cuDNN 벤치마크 활성화: 입력 크기별 최적 컨볼루션/연산 알고리즘 캐싱
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False

        # 2. Tensor Cores 활성화 (TF32): Ampere, Ada, Hopper 등에서 대폭 가속
        if hasattr(torch.backends.cuda, "matmul"):
            torch.backends.cuda.matmul.allow_tf32 = True
        if hasattr(torch.backends.cudnn, "allow_tf32"):
            torch.backends.cudnn.allow_tf32 = True

        # 3. GPU 메모리 캐시 정리
        torch.cuda.empty_cache()
        logger.info("[GPU 가속] CUDA cudnn.benchmark 및 TF32 가속 활성화 완료")

    elif device.type == "mps":
        logger.info("[GPU 가속] Apple Silicon MPS 가속 모드 활성화")


def get_optimal_dtype(device: torch.device) -> torch.dtype:
    """가속 디바이스에 맞는 최적의 반정밀도(FP16/BF16) 데이터 타입을 반환합니다."""
    if device.type == "cuda":
        if torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float16
    elif device.type == "mps":
        return torch.float16
    return torch.float32


# ==============================================================================
# LayaDecisionEngine — BaseDecisionEngine 구현체
# ==============================================================================

class LayaDecisionEngine(BaseDecisionEngine):
    """Laya 라이브러리 기반 의사결정 엔진.

    GPU 가속 로드 및 초고속 단일 포워드(System 1) 의사결정을 수행합니다.
    """

    DEFAULT_MODEL = "convaiinnovations/laya-multilingual"

    def __init__(self):
        self._device = get_optimal_device()
        configure_gpu_acceleration(self._device)
        self._dtype = get_optimal_dtype(self._device)
        self._pipeline: Optional[Any] = None
        self._model_name_or_path: str = self.DEFAULT_MODEL

    # ------------------------------------------------------------------
    # BaseDecisionEngine 인터페이스 구현
    # ------------------------------------------------------------------

    def initialize(self, model_name: Optional[str] = None, **kwargs: Any) -> None:
        """Laya Agent를 가속 디바이스(CUDA/MPS) 메모리에 로드합니다."""
        target_model = model_name or self._model_name_or_path

        if self._pipeline is not None and self._model_name_or_path == target_model:
            return

        logger.info(
            f"Laya Agent 로드 시작 (Model: {target_model}, Device: {self._device}, Dtype: {self._dtype})"
        )

        try:
            device_str = str(self._device)
            if target_model in (self.DEFAULT_MODEL, "multilingual", "ml"):
                pipeline = laya.load("convaiinnovations/laya", subfolder="multilingual", device=device_str, **kwargs)
            else:
                pipeline = laya.load(target_model, device=device_str, **kwargs)

            self._pipeline = pipeline
            self._model_name_or_path = target_model
            logger.info("Laya Agent GPU 가속 로드 완료")

        except Exception as e:
            logger.error(f"Laya Agent 로드 중 오류 발생: {e}", exc_info=True)
            raise e

    def decide(
        self,
        context: str,
        question: str,
        decision_type: str = "choice",
        options: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> DecisionResult:
        """GPU 가속 하에서 단일 포워드 패스로 결정을 도출합니다."""
        pipeline = self._get_pipeline()

        # inference_mode로 PyTorch 오버헤드 최소화
        with torch.inference_mode():
            autocast_ctx = (
                torch.autocast(device_type="cuda", dtype=self._dtype)
                if self._device.type == "cuda"
                else nullcontext()
            )

            with autocast_ctx:
                raw_result = self._call_laya_pipeline(
                    pipeline=pipeline,
                    context=context,
                    question=question,
                    decision_type=decision_type,
                    options=options,
                    **kwargs,
                )

        return self._format_decision_result(raw_result, options)

    def get_device_info(self) -> Dict[str, Any]:
        """현재 가속 하드웨어 및 VRAM 상태를 반환합니다."""
        info: Dict[str, Any] = {
            "device": str(self._device),
            "dtype": str(self._dtype),
            "is_cuda": self._device.type == "cuda",
            "is_mps": self._device.type == "mps",
            "pipeline_loaded": self._pipeline is not None,
            "model_name_or_path": self._model_name_or_path,
        }

        if self._device.type == "cuda":
            current_device_idx = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(current_device_idx)
            info.update({
                "gpu_name": props.name,
                "cuda_capability": f"{props.major}.{props.minor}",
                "total_vram_gb": round(props.total_memory / (1024 ** 3), 2),
                "allocated_vram_mb": round(torch.cuda.memory_allocated(current_device_idx) / (1024 ** 2), 2),
                "reserved_vram_mb": round(torch.cuda.memory_reserved(current_device_idx) / (1024 ** 2), 2),
            })
        elif self._device.type == "mps":
            info.update({
                "platform": "Apple Silicon MPS",
            })

        return info

    def clear_cache(self) -> None:
        """GPU VRAM 캐시를 비웁니다."""
        if self._device.type == "cuda":
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            logger.info("CUDA VRAM 캐시 정리 완료")
        elif self._device.type == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
            logger.info("MPS 캐시 정리 완료")

    @property
    def device_name(self) -> str:
        return str(self._device)

    @property
    def model_name_or_path(self) -> str:
        return self._model_name_or_path

    # ------------------------------------------------------------------
    # Laya 전용 내부 메서드
    # ------------------------------------------------------------------

    def _get_pipeline(self) -> Any:
        """파이프라인 인스턴스를 반환하며, 초기화되지 않았을 경우 자동 로드합니다."""
        if self._pipeline is None:
            self.initialize(self._model_name_or_path)
        return self._pipeline

    def _call_laya_pipeline(
        self,
        pipeline: Any,
        context: str,
        question: str,
        decision_type: str,
        options: Optional[List[str]],
        **kwargs: Any,
    ) -> Any:
        """다양한 Laya API 인터페이스를 지원하여 결정을 호출합니다."""
        q_payload: Dict[str, Any] = {
            "type": decision_type,
            "instructions": question,
        }
        if decision_type == "choice":
            q_payload["criteria"] = options or ["yes", "no"]
        elif decision_type == "score":
            q_payload["criteria"] = options or ["1", "2", "3", "4", "5"]
        elif decision_type == "noul":
            if options and len(options) >= 2:
                q_payload["criteria"] = {"false": options[0], "true": options[1]}

        questions_dict = {"decision_q": q_payload}

        # 1. system_one (Laya 공식 원샷 결정 인터페이스)
        if hasattr(pipeline, "system_one") and callable(pipeline.system_one):
            return pipeline.system_one(state=context, questions=questions_dict, **kwargs)

        # 2. predict 메서드
        if hasattr(pipeline, "predict") and callable(pipeline.predict):
            try:
                return pipeline.predict(
                    state=context,
                    questions=questions_dict,
                    **kwargs,
                )
            except Exception:
                pass

        # 3. decide 메서드
        if hasattr(pipeline, "decide") and callable(pipeline.decide):
            return pipeline.decide(
                context=context,
                question=question,
                type=decision_type,
                options=options,
                **kwargs,
            )

        # 4. __call__ 직접 호출 (다양한 인자 시그니처 대응)
        try:
            return pipeline(
                context=context,
                question=question,
                type=decision_type,
                options=options,
                **kwargs,
            )
        except TypeError:
            pass

        try:
            payload: Dict[str, Any] = {
                "context": context,
                "question": question,
                "type": decision_type,
            }
            if options:
                payload["options"] = options
            return pipeline(payload, **kwargs)
        except TypeError:
            pass

        return pipeline(context, question=question, options=options, **kwargs)

    def _format_decision_result(
        self, raw_result: Any, options: Optional[List[str]]
    ) -> DecisionResult:
        """Laya의 결과 형태를 파싱하여 표준 DecisionResult로 변환합니다."""
        decision: Optional[str] = None
        confidence: Optional[float] = None
        probabilities: Dict[str, float] = {}

        if isinstance(raw_result, dict):
            if "answers" in raw_result and isinstance(raw_result["answers"], dict):
                raw_result = raw_result["answers"]

            if "decision_q" in raw_result and isinstance(raw_result["decision_q"], dict):
                sub = raw_result["decision_q"]
                decision = (
                    sub.get("choice")
                    or sub.get("answer")
                    or sub.get("decision")
                    or (str(sub.get("score")) if "score" in sub else None)
                    or (str(sub.get("noul")) if "noul" in sub else None)
                )
                confidence = sub.get("answer_confidence") or sub.get("confidence")
                probabilities = sub.get("probabilities", {})

            elif "labels" in raw_result and "scores" in raw_result:
                labels = raw_result["labels"]
                scores = raw_result["scores"]
                if labels:
                    decision = labels[0]
                    confidence = float(scores[0]) if scores else None
                    probabilities = {str(k): round(float(v), 4) for k, v in zip(labels, scores)}

            elif "decision" in raw_result:
                decision = raw_result["decision"]
                confidence = raw_result.get("confidence")
                probabilities = raw_result.get("probabilities", {})
            elif "choice" in raw_result:
                decision = raw_result["choice"]
                confidence = raw_result.get("answer_confidence") or raw_result.get("confidence")
                probabilities = raw_result.get("probabilities", {})
            elif "answer" in raw_result:
                decision = raw_result["answer"]
                confidence = raw_result.get("answer_confidence") or raw_result.get("confidence")
                probabilities = raw_result.get("probabilities", {})

            elif len(raw_result) == 1 and isinstance(list(raw_result.values())[0], dict):
                inner = list(raw_result.values())[0]
                decision = (
                    inner.get("choice")
                    or inner.get("answer")
                    or inner.get("decision")
                    or (str(inner.get("score")) if "score" in inner else None)
                    or (str(inner.get("noul")) if "noul" in inner else None)
                )
                confidence = inner.get("answer_confidence") or inner.get("confidence")
                probabilities = inner.get("probabilities", {})
            else:
                decision = str(raw_result)

        elif isinstance(raw_result, (list, tuple)) and raw_result:
            decision = str(raw_result[0])
        else:
            decision = str(raw_result)

        return DecisionResult(
            decision=decision,
            confidence=confidence,
            probabilities=probabilities,
            raw=raw_result,
        )
