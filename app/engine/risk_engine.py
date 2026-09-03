import json
import time
from typing import Dict, Any, Optional

from app.common.db_conn import DbConn
from app.common.constants import RiskConstants
from app.common.logger import get_logger
from app.common.utils import RiskUtils
from app.llm import create_llm_client
from app.prompt.prompt_builder import PromptBuilder

logger = get_logger(__name__)


class RiskEngine:
    """위험성 평가 오케스트레이션 엔진.
    기존 BaseService._run / _run_sql 패턴을 따라
    DB 조회 → 프롬프트 조립 → LLM 호출 → 결과 저장 흐름을 관리합니다.
    """

    def __init__(self, config):
        """평가 엔진을 초기화합니다.

        Args:
            config: AppConfig 인스턴스 (DB, LLM 설정 포함)
        """
        self._config = config

    def _run_sql(self, action: str, query_key: str, params: dict) -> str:
        """기존 BaseService._run_sql 패턴을 따른 DB 실행 헬퍼.

        Args:
            action: DB 액션 (SELECT, INSERT, UPDATE, DELETE)
            query_key: SAFE_QUERY_REGISTRY의 쿼리 키
            params: 쿼리 바인딩 파라미터

        Returns:
            JSON 문자열 결과
        """
        net_value = self._config.get_db_net_value(action)
        net_value_json = json.dumps(net_value)

        db_conn = DbConn(net_value_json)

        query_data = {"query_key": query_key, "params": params}
        query_data_json = json.dumps(query_data)

        db_conn.create_request(query_data_json)
        return db_conn.create_response()

    def evaluate(
        self,
        domain_id: str,
        subject: str,
        request_type: str = RiskConstants.REALTIME,
    ) -> dict:
        """위험성 평가를 실행합니다.

        흐름:
        1. risk_request 레코드 생성 (PENDING)
        2. domain_config 로드
        3. 프롬프트 조립 (Syntax + Semantics)
        4. Gemma 호출
        5. 결과 파싱 → risk_result 저장
        6. risk_request 상태 업데이트 (COMPLETED)

        Args:
            domain_id: 도메인 식별자 (예: SECURITY)
            subject: 평가 주제 (예: FastAPI 서버 탈취)
            request_type: 요청 유형 (REALTIME, BATCH, REGENERATE)

        Returns:
            평가 요청 정보 + 결과 목록 딕셔너리
        """
        request_no = RiskUtils.get_rule_no()
        start_time = time.time()

        try:
            # ① risk_request 생성 (상태: PENDING)
            self._run_sql(RiskConstants.INSERT, "INSERT_RISK_REQUEST", {
                "rule_no": request_no,
                "domain_id": domain_id,
                "subject": subject,
                "request_type": request_type,
                "status": RiskConstants.PENDING,
                "total_threats": 0,
                "model_name": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "elapsed_ms": None,
                "completed_at": None,
            })

            # ② domain_config 조회
            domain_result = self._run_sql(
                RiskConstants.SELECT, "SELECT_DOMAIN_CONFIG_BY_ID", {"domain_id": domain_id}
            )
            domain_list = json.loads(domain_result)

            if not domain_list or not domain_list[0]:
                raise ValueError(f"[오류] 도메인 '{domain_id}'을 찾을 수 없거나 비활성 상태입니다.")

            domain_config = domain_list[0]

            # ③ 프롬프트 조립
            system_prompt = PromptBuilder.build_system_prompt(domain_config)
            user_prompt = PromptBuilder.build_user_prompt(subject)

            # ④ 상태 업데이트 (PROCESSING)
            self._run_sql(RiskConstants.UPDATE, "UPDATE_RISK_REQUEST_STATUS", {
                "rule_no": request_no,
                "status": RiskConstants.PROCESSING,
                "total_threats": 0,
                "model_name": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "elapsed_ms": None,
            })

            # ⑤ LLM 호출 (온도: 도메인 설정값, 없으면 평가 기본값)
            temperature = float(domain_config.get("temperature") or self._config.LLM_TEMPERATURE)
            llm_client = create_llm_client(
                provider=self._config.LLM_PROVIDER,
                base_url=self._config.LLM_BASE_URL,
                model=self._config.LLM_MODEL,
                api_key=self._config.LLM_API_KEY,
            )
            llm_response = llm_client.chat(system_prompt, user_prompt, temperature)

            # ⑥ 응답 파싱 (파싱 실패는 예외→FAILED, 정상 빈 배열은 그대로 진행)
            content = llm_response.get("content", "")
            risk_items = self._parse_risk_items(content)

            # ⑦ risk_result 건별 저장 (등급·점수는 서버 재계산값으로 통일)
            # LLM 오타(공백·표기 변형)는 허용값으로 정규화, 범위 밖은 중립값으로 보정
            for idx, item in enumerate(risk_items, start=1):
                likelihood = (item.get("likelihood") or "").strip()
                impact = (item.get("impact") or "").strip()
                if likelihood not in RiskConstants.LIKELIHOOD_VALUES:
                    logger.warning(f"[Engine] likelihood 값 보정: {likelihood!r} → '중간'")
                    likelihood = RiskConstants.LIKELIHOOD_MEDIUM
                if impact not in RiskConstants.IMPACT_VALUES:
                    logger.warning(f"[Engine] impact 값 보정: {impact!r} → '중간'")
                    impact = RiskConstants.IMPACT_MEDIUM
                item["likelihood"] = likelihood
                item["impact"] = impact
                risk_score = RiskUtils.calculate_risk_score(likelihood, impact)
                risk_level = RiskUtils.determine_risk_level(risk_score)
                item["risk_score"] = risk_score
                item["risk_level"] = risk_level

                self._run_sql(RiskConstants.INSERT, "INSERT_RISK_RESULT", {
                    "rule_no": RiskUtils.get_rule_no(),
                    "group_no": request_no,
                    "seq": idx,
                    "threat_name": item.get("threat_name", ""),
                    "category": item.get("category", ""),
                    "risk_level": risk_level,
                    "likelihood": likelihood,
                    "impact": impact,
                    "risk_score": risk_score,
                    "description": item.get("description", ""),
                    "mitigation": item.get("mitigation", ""),
                    "legal_basis": item.get("legal_basis", ""),
                })

            # ⑧ risk_request 상태 완료 + 저장 행 재조회 (시각은 DB 실값)
            elapsed_ms = int((time.time() - start_time) * 1000)
            self._run_sql(RiskConstants.UPDATE, "UPDATE_RISK_REQUEST_STATUS", {
                "rule_no": request_no,
                "status": RiskConstants.COMPLETED,
                "total_threats": len(risk_items),
                "model_name": llm_response.get("model", ""),
                "prompt_tokens": llm_response.get("prompt_tokens", 0),
                "completion_tokens": llm_response.get("completion_tokens", 0),
                "elapsed_ms": elapsed_ms,
            })
            stored_result = self._run_sql(
                RiskConstants.SELECT, "SELECT_RISK_REQUEST_BY_ID", {"rule_no": request_no}
            )
            stored_list = json.loads(stored_result)
            stored_row = stored_list[0] if stored_list and stored_list[0] else {}

            return {
                "rule_no": request_no,
                "domain_id": domain_id,
                "subject": subject,
                "status": RiskConstants.COMPLETED,
                "total_threats": len(risk_items),
                "model_name": llm_response.get("model", ""),
                "prompt_tokens": llm_response.get("prompt_tokens", 0),
                "completion_tokens": llm_response.get("completion_tokens", 0),
                "elapsed_ms": elapsed_ms,
                "created_at": str(stored_row.get("created_at", "")) or "",
                "completed_at": str(stored_row.get("completed_at", "")) or "",
                "results": risk_items,
            }

        except Exception as e:
            # 실패 시 상태 업데이트
            elapsed_ms = int((time.time() - start_time) * 1000)
            try:
                self._run_sql(RiskConstants.UPDATE, "UPDATE_RISK_REQUEST_STATUS", {
                    "rule_no": request_no,
                    "status": RiskConstants.FAILED,
                    "total_threats": 0,
                    "model_name": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "elapsed_ms": elapsed_ms,
                })
            except Exception:
                pass
            raise e

    def generate_domain_knowledge(
        self, domain_id: str, domain_name: str, role_description: str,
        example_subjects: Optional[str] = None,
    ) -> dict:
        """Gemma를 통해 도메인 전문 지식을 자동 생성합니다.

        Args:
            domain_id: 도메인 식별자
            domain_name: 도메인 표시명
            role_description: 전문가 역할 정의
            example_subjects: Few-shot 예시 주제 (미지정 시 없음)

        Returns:
            생성된 도메인 설정 딕셔너리
        """
        # ① Gemma에게 도메인 지식 생성 요청
        system_prompt = "너는 위험성 평가 도메인 지식 전문가다. 요청된 형식의 JSON으로만 응답하라."
        user_prompt = PromptBuilder.build_domain_generation_prompt(role_description)

        llm_client = create_llm_client(
            provider=self._config.LLM_PROVIDER,
            base_url=self._config.LLM_BASE_URL,
            model=self._config.LLM_MODEL,
            api_key=self._config.LLM_API_KEY,
        )
        llm_response = llm_client.chat(
            system_prompt, user_prompt,
            temperature=float(self._config.LLM_DOMAIN_GEN_TEMPERATURE),
        )

        # ② 응답 파싱
        content = llm_response.get("content", "")
        cleaned = self._clean_json_text(content)
        try:
            knowledge = json.loads(cleaned)
        except json.JSONDecodeError:
            knowledge = {"standards": "", "legal_references": "", "risk_categories": ""}

        # ③ domain_config 저장 (is_reviewed = false)
        rule_no = RiskUtils.get_rule_no()
        self._run_sql(RiskConstants.INSERT, "INSERT_DOMAIN_CONFIG", {
            "rule_no": rule_no,
            "domain_id": domain_id,
            "domain_name": domain_name,
            "role_description": role_description,
            "standards": knowledge.get("standards", ""),
            "legal_references": knowledge.get("legal_references", ""),
            "risk_categories": knowledge.get("risk_categories", ""),
            "output_instruction": PromptBuilder.DEFAULT_OUTPUT_INSTRUCTION,
            "example_subjects": example_subjects,
            "temperature": float(self._config.LLM_TEMPERATURE),
            "is_active": True,
            "is_reviewed": False,
        })

        # ④ 저장된 행을 다시 읽어 실제값으로 반환 (기본값·NULL 오표기 방지)
        stored_result = self._run_sql(
            RiskConstants.SELECT, "SELECT_DOMAIN_CONFIG_BY_ID", {"domain_id": domain_id}
        )
        stored_list = json.loads(stored_result)
        if stored_list and stored_list[0]:
            return stored_list[0]

        return {
            "rule_no": rule_no,
            "domain_id": domain_id,
            "domain_name": domain_name,
            "role_description": role_description,
            "standards": knowledge.get("standards", ""),
            "legal_references": knowledge.get("legal_references", ""),
            "risk_categories": knowledge.get("risk_categories", ""),
            "output_instruction": PromptBuilder.DEFAULT_OUTPUT_INSTRUCTION,
            "example_subjects": example_subjects,
            "temperature": float(self._config.LLM_TEMPERATURE),
            "is_active": True,
            "is_reviewed": False,
        }

    @staticmethod
    def _clean_json_text(content: str) -> str:
        """마크다운 코드 블록(```json ... ```)이나 앞뒤 공백을 제거합니다."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _parse_risk_items(content: str) -> list:
        """LLM 응답 텍스트에서 위험 항목 JSON 배열을 추출합니다.

        파싱 실패(깨진 JSON, 예상 밖 형태)는 ValueError를 올려 FAILED 처리하고,
        정상적으로 파싱된 빈 배열([])은 그대로 반환해 앱 로직에서 처리합니다.
        """
        cleaned = RiskEngine._clean_json_text(content)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"[Engine] LLM 응답 JSON 파싱 실패: {content[:200]}")
            raise ValueError(
                "[오류] LLM 응답이 유효한 JSON이 아닙니다. "
                f"(응답 앞부분: {content[:200]})"
            )
        # 최상위가 리스트인 경우 (빈 배열 포함)
        if isinstance(parsed, list):
            return parsed
        # 최상위가 딕셔너리이고 내부에 리스트가 있는 경우
        if isinstance(parsed, dict):
            for value in parsed.values():
                if isinstance(value, list):
                    return value
        logger.warning(f"[Engine] LLM 응답 형태 오류 (리스트 없음): {content[:200]}")
        raise ValueError(
            "[오류] LLM 응답에서 위험 항목 목록을 찾을 수 없습니다. "
            f"(응답 앞부분: {content[:200]})"
        )
