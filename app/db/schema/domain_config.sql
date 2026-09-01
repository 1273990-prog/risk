-- 도메인 설정 테이블
-- Gemma에게 "어떤 전문가로 행동하라"는 Semantics 지식을 저장합니다.
CREATE TABLE IF NOT EXISTS domain_config (
    rule_no             VARCHAR(51)     PRIMARY KEY,
    domain_id           VARCHAR(40)     UNIQUE NOT NULL,        -- 도메인 식별자 (예: SECURITY)
    domain_name         VARCHAR(100)    NOT NULL,               -- 도메인 표시명 (예: 보안 전문가)
    role_description    TEXT            NOT NULL,               -- 전문가 역할 정의
    standards           TEXT,                                   -- 판단 기준 표준 (Gemma 생성)
    legal_references    TEXT,                                   -- 관련 법규 (Gemma 생성)
    risk_categories     TEXT,                                   -- 위험 분류 체계 (Gemma 생성)
    output_instruction  TEXT,                                   -- 출력 형식 지시 (JSON 스키마)
    example_subjects    TEXT,                                   -- Few-shot 예시
    temperature         NUMERIC(3,2)    DEFAULT 0.30,           -- 추론 온도
    generated_at        TIMESTAMPTZ,                            -- 생성날짜
    is_active           BOOLEAN         DEFAULT true,           -- 활성/비활성
    is_reviewed         BOOLEAN         DEFAULT false,          -- 관리자 검토 완료 여부
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);
