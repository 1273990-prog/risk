class PromptBuilder:
    """프롬프트 조립기.
    domain_config의 Semantics 데이터를 Syntax 구조에 결합하여
    Gemma에 전달할 System Prompt를 생성합니다.
    """

    # ─── 공통 출력 형식 지시 (Syntax 고정) ───
    DEFAULT_OUTPUT_INSTRUCTION = """다음 JSON 배열 형식으로 응답하라. 정확히 10개 항목을 생성하라. 5개에서 멈추지 마라.
반드시 아래 스키마를 따르는 JSON 배열만 응답하고, 마크다운·설명문 등 다른 텍스트는 포함하지 마라.
[
  {
    "threat_name": "위험 항목명 (중복 금지)",
    "category": "위험 분류 (위 카테고리 목록 중에서만 선택)",
    "likelihood": "높음/중간/낮음",
    "impact": "높음/중간/낮음",
    "description": "상세 설명 (2~3문장)",
    "mitigation": "구체적 대응방안 (담당자·조치 단위로)",
    "legal_basis": "관련 법규 (형식: 법령명 제X조 제X항, 최대 2개, 해당 없으면 빈 문자열)"
  }
]
위 카테고리를 최소 1회씩 커버하라. 존재하지 않는 법규를 창작하지 마라."""

    @staticmethod
    def build_system_prompt(domain_config: dict) -> str:
        """도메인 설정에서 Semantics를 추출하여 System Prompt를 조립합니다.

        Args:
            domain_config: domain_config 테이블의 행 딕셔너리

        Returns:
            조립된 시스템 프롬프트 문자열
        """
        parts = []

        # 1. 전문가 역할 정의 (Semantics)
        role = domain_config.get("role_description", "")
        if role:
            parts.append(f"{role}")

        # 2. 판단 기준 표준 (Semantics — Gemma 생성)
        standards = domain_config.get("standards", "")
        if standards:
            parts.append(f"\n다음 기준으로 평가하라:\n{standards}")

        # 3. 법적 근거 (Semantics — Gemma 생성)
        legal_refs = domain_config.get("legal_references", "")
        if legal_refs:
            parts.append(f"\n법적 근거는 다음을 참조하라:\n{legal_refs}")

        # 4. 위험 분류 체계 (Semantics — Gemma 생성)
        categories = domain_config.get("risk_categories", "")
        if categories:
            parts.append(f"\n위험 분류는 다음 중에서 선택하라:\n{categories}")

        # 5. 출력 형식 지시 (Syntax 고정)
        output_inst = domain_config.get("output_instruction", "") or PromptBuilder.DEFAULT_OUTPUT_INSTRUCTION
        parts.append(f"\n{output_inst}")

        # 6. Few-shot 예시 (있을 경우)
        examples = domain_config.get("example_subjects", "")
        if examples:
            parts.append(f"\n참고 예시:\n{examples}")

        return "\n".join(parts)

    @staticmethod
    def build_domain_generation_prompt(role_description: str) -> str:
        """도메인 지식 자동 생성용 프롬프트를 조립합니다.
        Gemma에게 standards, legal_references, risk_categories를 생성하도록 지시합니다.

        Args:
            role_description: 전문가 역할 정의 (예: "정보보안 위험성 평가 전문가")

        Returns:
            도메인 지식 생성 요청 프롬프트
        """
        return f"""너는 {role_description}이다.

이 역할에서 위험성 평가를 수행할 때 참조해야 할 전문 지식을 작성하라.

다음 3개 항목을 반드시 포함하는 JSON 객체로 응답하라:

{{
  "standards": "위험성 평가 시 참조해야 할 국제/국내 표준 및 프레임워크 목록 (각 항목을 줄바꿈으로 구분)",
  "legal_references": "관련 법규 및 조항 목록 (각 항목을 줄바꿈으로 구분)",
  "risk_categories": "위험 분류 체계 목록 (쉼표로 구분)"
}}

구체적이고 실무에서 사용되는 항목만 포함하라."""

    @staticmethod
    def build_user_prompt(subject: str) -> str:
        """사용자 입력 주제로 User Prompt를 생성합니다.

        Args:
            subject: 평가 주제 (예: "FastAPI 서버 탈취")

        Returns:
            User Prompt 문자열
        """
        return f"다음 주제에 대한 위험성 평가를 수행하라: {subject}"
