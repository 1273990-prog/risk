import time
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Union

import torch
import laya
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.common.logger import get_logger

logger = get_logger(__name__)

# /v1/decision 및 기존 /api/v1/decision 모두 지원
router = APIRouter(tags=["의사결정 (Laya)"])


# ==============================================================================
# GPU 가속 및 최적화 설정 함수 (CUDA / Apple Silicon MPS / CPU)
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
    """Laya 초고속 결정을 위한 PyTorch GPU 하드웨어 가속 플래그를 설정합니다."""
    if device.type == "cuda":
        # 1. cuDNN 벤치마크 활성화: 입력 크기별 최적 컨볼루션/연산 알고리즘 캐싱
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False

        # 2. Tensor Cores 활성화 (TF32): Ampere(RTX 30xx), Ada(RTX 40xx), Hopper 등에서 대폭 가속
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
# LayaPipeline 싱글톤 관리자 (의사결정 전용)
# ==============================================================================

class LayaPipelineManager:
    """LayaPipeline의 GPU 가속 로드 및 초고속 단일 포워드(System 1) 의사결정을 관리하는 싱글톤 클래스"""

    _instance: Optional["LayaPipelineManager"] = None

    def __init__(self):
        self.device = get_optimal_device()
        configure_gpu_acceleration(self.device)
        self.dtype = get_optimal_dtype(self.device)
        self.pipeline: Optional[Any] = None
        # 다국어/한국어 지원 모델 기본값
        self.model_name_or_path: str = "convaiinnovations/laya-multilingual"

    @classmethod
    def get_instance(cls) -> "LayaPipelineManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize_pipeline(
        self,
        model_name_or_path: Optional[str] = None,
        force_reload: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Laya Agent를 가속 디바이스(CUDA/MPS) 메모리에 로드합니다."""
        target_model = model_name_or_path or self.model_name_or_path

        if self.pipeline is not None and not force_reload and self.model_name_or_path == target_model:
            return self.pipeline

        logger.info(
            f"Laya Agent 로드 시작 (Model: {target_model}, Device: {self.device}, Dtype: {self.dtype})"
        )

        try:
            device_str = str(self.device)
            if target_model in ("convaiinnovations/laya-multilingual", "multilingual", "ml"):
                pipeline = laya.load("convaiinnovations/laya", subfolder="multilingual", device=device_str, **kwargs)
            else:
                pipeline = laya.load(target_model, device=device_str, **kwargs)

            self.pipeline = pipeline
            self.model_name_or_path = target_model
            logger.info("Laya Agent GPU 가속 로드 완료")
            return self.pipeline

        except Exception as e:
            logger.error(f"Laya Agent 로드 중 오류 발생: {e}", exc_info=True)
            raise e

    def get_pipeline(self) -> Any:
        """파이프라인 인스턴스를 반환하며, 초기화되지 않았을 경우 자동 로드합니다."""
        if self.pipeline is None:
            self.initialize_pipeline(self.model_name_or_path)
        return self.pipeline

    def decide(
        self,
        context: str,
        question: str,
        decision_type: str = "choice",
        options: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """GPU 가속 하에서 단일 포워드 패스로 결정을 도출합니다."""
        pipeline = self.get_pipeline()

        # inference_mode로 PyTorch 오버헤드 최소화
        with torch.inference_mode():
            autocast_ctx = (
                torch.autocast(device_type="cuda", dtype=self.dtype)
                if self.device.type == "cuda"
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
    ) -> Dict[str, Any]:
        """Laya의 결과 형태(dict/list/object)를 파싱하여 표준 결정 응답 포맷으로 정리합니다."""
        decision: Optional[str] = None
        confidence: Optional[float] = None
        probabilities: Dict[str, float] = {}

        if isinstance(raw_result, dict):
            # Laya predict_batch 결과 구조인 경우: {"model": "...", "answers": {...}, "usage": ...}
            if "answers" in raw_result and isinstance(raw_result["answers"], dict):
                raw_result = raw_result["answers"]

            # Laya system_one 형식: {"decision_q": {"choice": "...", "probabilities": {...}, "answer_confidence": 0.98}}
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

            # Hugging Face Zero-shot 형식: {"labels": [...], "scores": [...]}
            elif "labels" in raw_result and "scores" in raw_result:
                labels = raw_result["labels"]
                scores = raw_result["scores"]
                if labels:
                    decision = labels[0]
                    confidence = float(scores[0]) if scores else None
                    probabilities = {str(k): round(float(v), 4) for k, v in zip(labels, scores)}

            # 직접 키 형식: {"decision": "...", "confidence": 0.98} 또는 {"answer": "..."}
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

            # 단일 중첩 딕셔너리 형태
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

        # confidence 소수점 정리
        if confidence is not None:
            confidence = round(float(confidence), 4)

        return {
            "decision": decision,
            "confidence": confidence,
            "probabilities": probabilities,
            "raw": raw_result,
        }

    def get_device_info(self) -> Dict[str, Any]:
        """현재 가속 하드웨어 및 VRAM 상태를 반환합니다."""
        info: Dict[str, Any] = {
            "device": str(self.device),
            "dtype": str(self.dtype),
            "is_cuda": self.device.type == "cuda",
            "is_mps": self.device.type == "mps",
            "pipeline_loaded": self.pipeline is not None,
            "model_name_or_path": self.model_name_or_path,
        }

        if self.device.type == "cuda":
            current_device_idx = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(current_device_idx)
            info.update({
                "gpu_name": props.name,
                "cuda_capability": f"{props.major}.{props.minor}",
                "total_vram_gb": round(props.total_memory / (1024 ** 3), 2),
                "allocated_vram_mb": round(torch.cuda.memory_allocated(current_device_idx) / (1024 ** 2), 2),
                "reserved_vram_mb": round(torch.cuda.memory_reserved(current_device_idx) / (1024 ** 2), 2),
            })
        elif self.device.type == "mps":
            info.update({
                "platform": "Apple Silicon MPS",
            })

        return info

    def clear_cache(self):
        """GPU VRAM 캐시를 비웁니다."""
        if self.device.type == "cuda":
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            logger.info("CUDA VRAM 캐시 정리 완료")
        elif self.device.type == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
            logger.info("MPS 캐시 정리 완료")


pipeline_manager = LayaPipelineManager.get_instance()


# ==============================================================================
# Pydantic 모델 정의
# ==============================================================================

class DecisionRequest(BaseModel):
    """의사결정(Decision) 요청 모델"""
    context: str = Field(
        ...,
        description="평가 대상 텍스트 상태(State / Context)",
        example="🎉축하합니다! 당첨금 1,000만 원 수령을 위해 아래 링크를 즉시 클릭하세요.",
    )
    question: str = Field(
        ...,
        description="결정할 질문(Question)",
        example="이 메시지의 카테고리는 무엇인가요?",
    )
    type: str = Field(
        default="choice",
        description="결정 유형 (choice: 다지선다, score: 척도 평가, noul: 참/거짓 확률)",
        example="choice",
    )
    options: Optional[List[str]] = Field(
        default=None,
        description="선택지 목록 (type이 choice일 때 필수)",
        example=["정상 알림", "스팸 광고", "고객 문의"],
    )
    model_name: Optional[str] = Field(
        default=None,
        description="사용할 Laya 모델 체크포인트 (기본: convaiinnovations/laya-multilingual)",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="추가 추론 파라미터",
    )


class DecisionResponse(BaseModel):
    """의사결정(Decision) 응답 모델"""
    decision: Optional[str] = Field(..., description="최종 결정된 항목 (선택된 옵션)")
    confidence: Optional[float] = Field(None, description="결정 신뢰도 (0.0 ~ 1.0)")
    probabilities: Optional[Dict[str, float]] = Field(default_factory=dict, description="선택지별 확률 분포")
    question: str = Field(..., description="입력된 질문")
    type: str = Field(..., description="결정 유형")
    elapsed_ms: float = Field(..., description="GPU 가속 소요 시간(ms)")
    device: str = Field(..., description="연산에 사용된 디바이스")
    raw: Optional[Any] = Field(None, description="Laya 모델 원본 응답")


# ==============================================================================
# API 라우트 정의
# ==============================================================================

@router.post("/v1/decision", response_model=DecisionResponse)
@router.post("/v1/decision/", response_model=DecisionResponse)
@router.post("/api/v1/decision", response_model=DecisionResponse)
@router.post("/api/v1/decision/", response_model=DecisionResponse)
async def make_decision(request: DecisionRequest):
    """Laya 비생성형 의사결정 모델을 통해 텍스트 상태(Context)와 질문(Question)으로부터
    최적의 선택(Choice)과 확률 분포를 초고속(Single Forward Pass)으로 결정합니다.
    """
    start_time = time.time()

    # 모델 변경 요청 시 리로드
    if request.model_name and request.model_name != pipeline_manager.model_name_or_path:
        try:
            pipeline_manager.initialize_pipeline(model_name_or_path=request.model_name)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Laya 모델 '{request.model_name}' 로드 실패: {str(e)}",
            )

    try:
        # GPU 가속 의사결정 실행
        result = pipeline_manager.decide(
            context=request.context,
            question=request.question,
            decision_type=request.type,
            options=request.options,
            **(request.parameters or {}),
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return DecisionResponse(
            decision=result.get("decision"),
            confidence=result.get("confidence"),
            probabilities=result.get("probabilities", {}),
            question=request.question,
            type=request.type,
            elapsed_ms=elapsed_ms,
            device=str(pipeline_manager.device),
            raw=result.get("raw"),
        )

    except Exception as e:
        logger.error(f"Laya 의사결정 처리 중 예외 발생: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"의사결정 실행 실패: {str(e)}",
        )


@router.get("/v1/decision/device")
@router.get("/api/v1/decision/device")
async def get_device_status():
    """현재 가속 디바이스 및 VRAM 사용 현황을 확인합니다."""
    return {
        "status": "ok",
        "device_info": pipeline_manager.get_device_info(),
    }


@router.post("/v1/decision/clear-cache")
@router.post("/api/v1/decision/clear-cache")
async def clear_gpu_cache():
    """GPU VRAM 캐시를 비웁니다."""
    pipeline_manager.clear_cache()
    return {
        "status": "success",
        "message": "GPU 캐시가 정리되었습니다.",
        "device_info": pipeline_manager.get_device_info(),
    }
