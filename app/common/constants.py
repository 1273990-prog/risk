from typing import Final


class RiskConstants:
    """위험성 평가 시스템 공통 상수 정의."""

    # ─── 위험도 (Risk Level) ───
    HIGH: Final[str] = "상"
    MEDIUM: Final[str] = "중"
    LOW: Final[str] = "하"

    # ─── 발생 가능성 (Likelihood) ───
    LIKELIHOOD_HIGH: Final[str] = "높음"
    LIKELIHOOD_MEDIUM: Final[str] = "중간"
    LIKELIHOOD_LOW: Final[str] = "낮음"

    # ─── 영향도 (Impact) ───
    IMPACT_HIGH: Final[str] = "높음"
    IMPACT_MEDIUM: Final[str] = "중간"
    IMPACT_LOW: Final[str] = "낮음"

    # ─── 요청 유형 (Request Type) ───
    REALTIME: Final[str] = "REALTIME"
    BATCH: Final[str] = "BATCH"
    REGENERATE: Final[str] = "REGENERATE"

    # ─── 처리 상태 (Status) ───
    PENDING: Final[str] = "PENDING"
    PROCESSING: Final[str] = "PROCESSING"
    COMPLETED: Final[str] = "COMPLETED"
    FAILED: Final[str] = "FAILED"

    # ─── DB Actions ───
    SELECT: Final[str] = "SELECT"
    INSERT: Final[str] = "INSERT"
    UPDATE: Final[str] = "UPDATE"
    DELETE: Final[str] = "DELETE"

    # ─── 위험 점수 매트릭스 (발생가능성 × 영향도 → 점수) ───
    RISK_SCORE_MATRIX = {
        ("높음", "높음"): 9,
        ("높음", "중간"): 6,
        ("높음", "낮음"): 3,
        ("중간", "높음"): 6,
        ("중간", "중간"): 4,
        ("중간", "낮음"): 2,
        ("낮음", "높음"): 3,
        ("낮음", "중간"): 2,
        ("낮음", "낮음"): 1,
    }
