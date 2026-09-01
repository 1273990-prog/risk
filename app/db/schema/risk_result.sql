-- 평가 결과 테이블
-- Gemma가 생성한 위험 항목을 건별로 저장합니다.
CREATE TABLE IF NOT EXISTS risk_result (
    rule_no         VARCHAR(51)     PRIMARY KEY,
    group_no        VARCHAR(51)     NOT NULL REFERENCES risk_request(rule_no),   -- 평가 요청 FK
    seq             INTEGER         NOT NULL,               -- 항목 순번
    threat_name     TEXT            NOT NULL,               -- 위험 항목명
    category        TEXT,                                   -- 위험 분류 (도메인 카테고리 중 선택)
    risk_level      VARCHAR(40),                            -- 위험도 (상/중/하)
    likelihood      VARCHAR(40),                            -- 발생 가능성 (높음/중간/낮음)
    impact          VARCHAR(40),                            -- 영향도 (높음/중간/낮음)
    risk_score      INTEGER,                                -- 위험 점수 (1~9, 가능성×영향도)
    description     TEXT,                                   -- 상세 설명
    mitigation      TEXT,                                   -- 대응방안
    legal_basis     TEXT,                           -- 관련 법규 조항
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);
