# AI DQN Ensemble 기반 Binance USDT Futures 시스템 운영 설계서

## 1. 목표 및 범위

이 문서는 **실제 운영 가능한 수준**으로 다음을 모두 포함한 트레이딩 플랫폼 설계를 정의한다.

- 전략 백테스팅
- 모의거래(페이퍼트레이딩)
- 실거래
- 전략 파라미터 GUI
- 학습 파라미터/세션 관리
- 리스크 제어 및 비상정지
- 도커 기반 배포

핵심 제약:

1. 전략 코드는 아래 로직을 **그대로** 사용(수식/흐름 변경 금지)
2. Frontend: React(TypeScript) + Zustand(또는 RTK) + TradingView Lightweight Charts
3. Backend: FastAPI(async), WebSocket 실시간 스트리밍, Background Worker
4. Database: MySQL + SQLAlchemy ORM + Alembic
5. 거래소: Binance USDT Futures, Binance 지원 전 타임프레임

---

## 2. 전략 규격(고정 로직)

아래 함수는 전략 의사결정 엔진의 기준 구현이며, 운영 시스템에서는 이 함수와 동등한 결과를 내는 구현만 허용한다.

```python
def _ai_dqn_ensemble(closes, highs, lows, volumes, p, price, atr):

    state_bins = int(p.get("state_bins", 3))
    gamma_ = p.get("gamma", 0.9)
    min_votes = int(p.get("min_votes", 3))
    adx_filter = p.get("adx_filter", 20)
    epsilon_ = p.get("epsilon", 0.1)
    sl, tp = p.get("atr_sl", 2.5), p.get("atr_tp", 3.5)

    if len(closes) < 60:
        return NONE

    adx = calc_adx(highs, lows, closes, 14)
    if adx[-1] is not None and adx[-1] < adx_filter:
        return NONE

    def disc(v, lo_, hi_, bins):
        return min(int((max(lo_, min(hi_, v)) - lo_) / (hi_ - lo_) * bins), bins - 1)

    def get_state(i):
        if i < 30:
            return None

        e20 = ema(closes[:i+1], 20)
        e50 = ema(closes[:i+1], 50)

        trend = (e20[-1] - e50[-1]) / e50[-1] * 100 if (e20[-1] and e50[-1] and e50[-1] > 0) else 0
        mom = (closes[i] - closes[i-10]) / closes[i-10] * 100 if closes[i-10] > 0 else 0

        rets = [(closes[j]-closes[j-1])/closes[j-1] for j in range(max(1,i-19),i+1) if closes[j-1]]
        vola = math.sqrt(sum(r**2 for r in rets)/len(rets)) * 100 if rets else 0

        rv = calc_rsi(closes[:i+1], 14)
        rsi_ = rv[-1] if rv[-1] is not None else 50

        return (
            disc(trend,-3,3,state_bins),
            disc(mom,-5,5,state_bins),
            disc(vola,0,3,state_bins),
            disc(rsi_,20,80,state_bins)
        )

    q_table = {}
    lr_q = 0.05
    rw = 5

    for i in range(30, len(closes) - rw - 1):
        st = get_state(i)
        if st is None:
            continue

        if st not in q_table:
            q_table[st] = [0.0, 0.0, 0.0]

        future_ret = (closes[i + rw] - closes[i]) / closes[i]
        atr_norm = atr / price if price > 0 else 0.01

        r_long = future_ret / atr_norm
        r_short = -future_ret / atr_norm
        r_hold = -abs(future_ret) / atr_norm * 0.1

        q = q_table[st]

        q[0] += lr_q * (r_hold + gamma_ * max(q) - q[0])
        q[1] += lr_q * (r_long + gamma_ * max(q) - q[1])
        q[2] += lr_q * (r_short + gamma_ * max(q) - q[2])

    cur_st = get_state(len(closes) - 1)

    if cur_st is None or cur_st not in q_table:
        return NONE

    random.seed(int(price * 100) % 99991)

    if random.random() < epsilon_:
        return NONE

    q_vals = q_table[cur_st]
    dqn_action = q_vals.index(max(q_vals))

    if q_vals[dqn_action] <= q_vals[0] * 1.1:
        return NONE

    return dqn_action
```

### 2.1 전략 엔진 구현 정책

- `StrategyAdapter` 계층에서 위 함수에 필요한 입력(`closes/highs/lows/volumes/p/price/atr`)을 정규화한다.
- `NONE=0, LONG=1, SHORT=2`와 같은 enum 매핑은 API/DB/UI 전구간 동일하게 관리한다.
- 백테스트/모의/실거래 모두 동일한 `DecisionCore`를 사용해 결정 일관성을 보장한다.
- **금지사항**: 수익함수, 상태정의, epsilon 처리, adx 필터, q-update 로직 변경 금지.

---

## 3. 전체 시스템 아키텍처

## 3.1 논리 아키텍처

1. **Frontend App (React + TS)**
   - 전략 설정/실행/모니터링
   - 실시간 차트(캔들/시그널/SLTP/자산곡선/DD)
   - WebSocket 구독으로 PnL/체결/상태 반영

2. **API Gateway (FastAPI Async)**
   - 인증/인가(JWT + RBAC)
   - 전략/백테스트/세션 관리 REST API
   - WebSocket fan-out 허브

3. **Backtest Worker**
   - 히스토리컬 데이터 수집 + 이벤트 기반 시뮬레이션
   - 성과지표 계산 및 결과 저장

4. **Live/Paper Trade Worker**
   - Binance WS 수신, 주문 실행(실거래 또는 가상)
   - 리스크 엔진 검사 후 주문 허용/거부

5. **Risk Engine Service(내부 모듈 또는 별도 서비스)**
   - 최대 레버리지 제한
   - 최대 일 손실 제한
   - 긴급 정지(e-stop)

6. **Data Layer**
   - MySQL: 정형데이터(계정, 설정, 주문, 포지션, 지표)
   - Redis: 캐시/큐/세션/스트림 오프셋
   - Object Storage(S3/MinIO): 백테스트 대용량 결과(JSON/Parquet)

7. **Message Bus / Queue**
   - Celery + Redis/RabbitMQ
   - 작업 종류: `backtest.run`, `live.tick`, `risk.check`, `report.generate`

8. **Exchange Connector**
   - Binance Futures REST/WS 통신
   - 재시도, rate limit, listenKey 갱신

## 3.2 데이터 흐름

- 백테스트: UI 요청 → API Job 생성 → Worker 실행 → DB/Object 저장 → WS/폴링으로 결과 반영
- 모의거래: Binance WS tick → Live Worker 신호생성 → Paper Broker 체결 → PnL 계산 → UI push
- 실거래: tick → 신호 → Risk Check → Binance 주문 → 체결확인 → 포지션/PnL 갱신 → UI push

---

## 4. DB 스키마 설계 (MySQL + SQLAlchemy + Alembic)

## 4.1 핵심 엔터티

### users
- id (PK)
- email (unique)
- password_hash
- role (admin, trader, viewer)
- is_active
- created_at, updated_at

### api_credentials
- id (PK)
- user_id (FK users.id)
- exchange (`binance_futures`)
- api_key_enc (AES-GCM 암호문)
- api_secret_enc (AES-GCM 암호문)
- key_version (KMS/HSM key rotation)
- is_enabled
- created_at, updated_at

### strategy_profiles
- id (PK)
- user_id (FK)
- name
- description
- timeframe (e.g. 1m, 3m, 5m, 1h, 1d … Binance 지원 전체)
- symbol (e.g. BTCUSDT)
- params_json (전략 파라미터 전체)
- is_active
- created_at, updated_at

### learning_sessions
- id (PK)
- strategy_profile_id (FK)
- gamma
- state_bins
- lr_q
- epsilon
- min_votes
- adx_filter
- started_at, ended_at
- notes
- metrics_json

### backtest_jobs
- id (PK)
- user_id (FK)
- strategy_profile_id (FK)
- symbol
- timeframe
- start_at, end_at
- fee_bps
- slippage_bps
- funding_model (historical/fixed)
- leverage
- status (queued/running/succeeded/failed)
- progress_pct
- error_message
- created_at, started_at, finished_at

### backtest_results
- id (PK)
- backtest_job_id (FK)
- total_return
- sharpe
- mdd
- win_rate
- profit_factor
- expectancy
- equity_curve_uri (object storage path)
- drawdown_curve_uri
- trades_uri
- summary_json

### backtest_trades
- id (PK)
- backtest_job_id (FK)
- ts_open, ts_close
- side (long/short)
- qty
- entry_price, exit_price
- fee, slippage_cost, funding_cost
- pnl, pnl_pct
- sl_price, tp_price
- reason_open, reason_close

### runtime_sessions
- id (PK)
- user_id (FK)
- strategy_profile_id (FK)
- mode (paper/live)
- symbol, timeframe
- status (starting/running/stopped/error)
- started_at, stopped_at
- last_heartbeat

### orders
- id (PK)
- runtime_session_id (FK)
- exchange_order_id
- client_order_id
- symbol
- side
- order_type
- qty
- price
- status
- reduce_only
- leverage
- raw_json
- created_at, updated_at

### fills
- id (PK)
- order_id (FK)
- fill_price
- fill_qty
- fee
- fee_asset
- filled_at

### positions
- id (PK)
- runtime_session_id (FK)
- symbol
- side
- qty
- avg_entry
- mark_price
- unrealized_pnl
- realized_pnl
- liquidation_price
- leverage
- updated_at

### risk_limits
- id (PK)
- user_id (FK)
- max_leverage
- max_daily_loss_pct
- max_notional_per_symbol
- emergency_stop_enabled
- updated_at

### risk_events
- id (PK)
- runtime_session_id (FK nullable)
- event_type (leverage_violation, daily_loss_breach, estop_triggered)
- severity
- detail_json
- created_at

### audit_logs
- id (PK)
- user_id (FK nullable)
- action
- target_type
- target_id
- metadata_json
- created_at

## 4.2 인덱스/파티셔닝

- `backtest_jobs(status, created_at)` 복합 인덱스
- `orders(runtime_session_id, created_at)` 인덱스
- `fills(order_id, filled_at)` 인덱스
- `backtest_trades(backtest_job_id, ts_open)` 인덱스
- 대용량 시계열(`fills`, `risk_events`)은 월 단위 파티션 고려

## 4.3 마이그레이션 운영

- Alembic revision은 기능 단위로 분리
- `expand/contract` 패턴으로 무중단 마이그레이션
- DB schema hash를 CI 단계에서 검증

---

## 5. 백엔드 폴더 구조 (FastAPI)

```text
backend/
  app/
    main.py
    core/
      config.py
      logging.py
      security.py
      encryption.py
      db.py
      exceptions.py
    api/
      deps.py
      v1/
        auth.py
        strategy.py
        backtest.py
        runtime.py
        risk.py
        ws.py
    models/
      user.py
      api_credentials.py
      strategy_profile.py
      learning_session.py
      backtest_job.py
      backtest_result.py
      backtest_trade.py
      runtime_session.py
      order.py
      fill.py
      position.py
      risk_limit.py
      risk_event.py
      audit_log.py
    schemas/
      auth.py
      strategy.py
      backtest.py
      runtime.py
      risk.py
      common.py
    repositories/
      user_repo.py
      strategy_repo.py
      backtest_repo.py
      runtime_repo.py
      risk_repo.py
    services/
      strategy/
        indicators.py
        decision_core.py      # _ai_dqn_ensemble 포팅/검증
        signal_service.py
      backtest/
        data_loader.py
        execution_model.py
        metrics.py
        engine.py
      runtime/
        ws_client.py
        order_router.py
        pnl_service.py
        session_service.py
      risk/
        rules.py
        guard.py
        estop.py
      exchange/
        binance_rest.py
        binance_ws.py
      notifier/
        ws_hub.py
        event_bus.py
    workers/
      celery_app.py
      tasks_backtest.py
      tasks_runtime.py
      tasks_maintenance.py
    alembic/
      versions/
    tests/
      unit/
      integration/
      e2e/
```

설계 원칙:
- API 계층은 입출력 검증/인증만 담당
- 전략/백테스트/리스크 핵심 로직은 `services/`로 집약
- 거래소 통신과 주문 라우팅 분리(테스트 용이성 확보)

---

## 6. 프론트 폴더 구조 (React + TypeScript + Zustand)

```text
frontend/
  src/
    app/
      router.tsx
      providers.tsx
      store.ts
    pages/
      DashboardPage.tsx
      BacktestPage.tsx
      PaperTradingPage.tsx
      LiveTradingPage.tsx
      StrategySettingsPage.tsx
      LearningSessionsPage.tsx
      RiskControlPage.tsx
    features/
      auth/
      strategy/
        components/
          StrategyForm.tsx
          ParameterTooltip.tsx
          StrategyExplanationPanel.tsx
        api.ts
        store.ts
      backtest/
        components/
          BacktestRunForm.tsx
          MetricsCards.tsx
          TradesTable.tsx
          EquityDrawdownChart.tsx
          SignalOverlayChart.tsx
        api.ts
        store.ts
      runtime/
        components/
          RuntimeControlPanel.tsx
          RealtimePnLPanel.tsx
          FillLogTable.tsx
          PositionPanel.tsx
        ws.ts
        store.ts
      risk/
        components/
          RiskLimitsForm.tsx
          EmergencyStopButton.tsx
        api.ts
        store.ts
    components/
      layout/
      common/
    lib/
      httpClient.ts
      wsClient.ts
      format.ts
      chart/
        lightweightChart.ts
        seriesBuilders.ts
    types/
      api.ts
      domain.ts
    styles/
      theme.css
```

UI 필수 구성:
- 파라미터 입력 시 tooltip: 각 파라미터 의미/권장범위/리스크
- 전략 설명 패널: DQN 개념, Ensemble 개념, 전략 리스크 특성
- 차트 오버레이:
  - 진입/청산 마커
  - SL/TP 라인
  - 자산곡선/드로우다운 패널

---

## 7. API 엔드포인트 설계

Base: `/api/v1`

## 7.1 인증
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

## 7.2 전략/파라미터
- `GET /strategies`
- `POST /strategies`
- `GET /strategies/{id}`
- `PUT /strategies/{id}`
- `DELETE /strategies/{id}`
- `POST /strategies/{id}/validate` (파라미터 유효성/범위 검증)

## 7.3 학습 세션
- `POST /learning-sessions`
- `GET /learning-sessions`
- `GET /learning-sessions/{id}`
- `POST /learning-sessions/{id}/stop`

## 7.4 백테스트
- `POST /backtests` (기간/타임프레임/수수료/슬리피지/펀딩비/레버리지 포함)
- `GET /backtests`
- `GET /backtests/{id}`
- `GET /backtests/{id}/trades`
- `GET /backtests/{id}/equity`
- `GET /backtests/{id}/drawdown`
- `POST /backtests/{id}/cancel`

## 7.5 모의/실거래 런타임
- `POST /runtime/sessions` (mode=paper|live)
- `GET /runtime/sessions`
- `GET /runtime/sessions/{id}`
- `POST /runtime/sessions/{id}/stop`
- `GET /runtime/sessions/{id}/orders`
- `GET /runtime/sessions/{id}/fills`
- `GET /runtime/sessions/{id}/positions`
- `GET /runtime/sessions/{id}/pnl`

## 7.6 리스크/보안
- `GET /risk/limits`
- `PUT /risk/limits`
- `POST /risk/emergency-stop`
- `POST /risk/emergency-resume`
- `GET /risk/events`
- `POST /credentials/binance` (API key 암호화 저장)
- `DELETE /credentials/binance/{id}`

## 7.7 WebSocket 채널
- `/ws/runtime/{session_id}`
  - 이벤트: `tick`, `signal`, `order`, `fill`, `position`, `pnl`, `risk_event`, `session_status`
- `/ws/backtests/{job_id}`
  - 이벤트: `progress`, `metric_update`, `completed`, `failed`

---

## 8. 백테스트 엔진 구조

## 8.1 컴포넌트

1. `HistoricalDataProvider`
   - Binance klines + funding rate + mark price 수집
   - timeframe별 리샘플링(원본 보존)

2. `FeatureBuilder`
   - ATR/ADX/EMA/RSI 계산
   - 전략 함수 입력 시계열 생성

3. `SignalEngine`
   - `_ai_dqn_ensemble` 호출
   - 바 단위 의사결정(look-ahead 방지)

4. `ExecutionSimulator`
   - 주문 체결가 = 시뮬레이터 가격 + 슬리피지
   - 수수료/펀딩비/레버리지 반영
   - SL/TP 히트 이벤트 처리(우선순위 규칙 고정)

5. `PortfolioEngine`
   - 포지션/현금/증거금/청산위험 계산

6. `MetricsEngine`
   - 총 수익률
   - Sharpe
   - MDD
   - 승률
   - Profit Factor
   - Expectancy

## 8.2 이벤트 루프

- 각 캔들 close 시점마다:
  1) feature 업데이트
  2) 신호 생성
  3) 리스크/자금 제약 확인
  4) 주문/포지션 업데이트
  5) 자산곡선/드로우다운 기록

## 8.3 결과 산출

- `summary_json`: 전체 메트릭
- `trades`: 진입/청산, 비용(수수료/슬리피지/펀딩)
- `equity_curve`, `drawdown_curve`
- 차트 표시용 `markers` (buy/sell/sl/tp)

---

## 9. 실시간 엔진 구조 (모의/실거래 공통)

## 9.1 런타임 파이프라인

1. Binance WS 수신
   - klines, markPrice, userDataStream(실거래)
2. Candle Aggregator
   - timeframe별 완성 캔들 생성
3. Decision Step
   - 전략 함수 호출로 `NONE/LONG/SHORT` 결정
4. Risk Gate
   - 주문 전 검증(레버리지, 일손실, estop)
5. Broker Adapter
   - paper: 내부 fill 모델
   - live: Binance 주문 API
6. State Store
   - 주문/체결/포지션/PnL 저장
7. WS Broadcast
   - UI에 실시간 전송

## 9.2 신뢰성

- WS 끊김 시 자동 재연결 + 백오프
- listenKey 주기 갱신
- 중복 체결 방지(idempotency key)
- 세션 heartbeat 모니터링

## 9.3 모의거래 체결 모델

- 기본: mid/last 기반 즉시체결 + 슬리피지
- 옵션: orderbook depth 기반 체결지연 모델
- 실시간 PnL = mark price 기준

---

## 10. 리스크 엔진 설계

## 10.1 규칙

1. **최대 레버리지 제한**
   - 주문 시 요청 레버리지 ≤ 사용자 limit
2. **최대 일 손실 제한**
   - UTC 일자 기준 누적 실현손익 + 미실현 반영 옵션
   - 임계치 도달 시 신규 진입 차단/강제 축소 정책
3. **긴급 정지 버튼(E-Stop)**
   - 즉시 신규주문 차단
   - 선택 옵션: 오픈 포지션 시장가 청산

## 10.2 실행 시점

- Pre-trade check: 주문 전
- Post-trade check: 체결 직후
- Periodic check: 1~5초 주기

## 10.3 장애 대응

- 리스크 엔진 장애 시 Fail-Closed (주문 차단)
- 모든 차단 이벤트 `risk_events` + `audit_logs` 기록

---

## 11. 파라미터 GUI 및 설명 설계

## 11.1 사용자 수정 가능 파라미터

- `gamma`
- `state_bins`
- `lr_q` (학습계수, 현재 전략 코드 고정값 0.05와 분리 운영 시 버전관리 필요)
- `epsilon`
- `min_votes`
- `adx_filter`
- `atr_sl`
- `atr_tp`

## 11.2 UX 요구

- 입력 컴포넌트: number + slider + validation message
- Tooltip: 정의, 수학적 영향, 실무 리스크
- Preset: 보수형/중립형/공격형
- 설명 패널:
  - DQN: 상태-행동 가치(Q) 기반 정책
  - Ensemble: 여러 신호 결합/필터링으로 노이즈 완화
  - 리스크 특성: 횡보장 손실 가능성, 변동성 급증 구간 민감도

## 11.3 버전 관리

- 전략 파라미터 변경 시 immutable snapshot 저장
- 런타임 세션은 snapshot id를 참조해 재현성 보장

---

## 12. Docker 배포 설계

## 12.1 서비스 구성 (docker-compose 기준)

- `frontend` (React build + Nginx)
- `api` (FastAPI + Uvicorn/Gunicorn)
- `worker` (Celery worker)
- `beat` (Celery beat 스케줄러)
- `mysql`
- `redis`
- `minio` (선택)
- `prometheus` + `grafana` (모니터링)

## 12.2 네트워크/보안

- 내부 네트워크 분리(`backend_net`, `data_net`)
- API는 HTTPS reverse proxy(Traefik/Nginx)
- 비밀정보는 env 파일 대신 Secret Manager/KMS 연동

## 12.3 CI/CD

1. lint/test/build
2. Alembic migration dry-run
3. Docker image build & scan
4. staging 배포 후 smoke test
5. production 롤링 배포

## 12.4 관측성

- 애플리케이션 로그: JSON 구조화
- 메트릭:
  - 주문 성공률/지연
  - WS reconnect 횟수
  - 백테스트 처리시간
  - 리스크 차단 건수
- 알림: Slack/PagerDuty(Webhook)

---

## 13. 운영 체크리스트

1. Binance testnet/live 환경 분리
2. API key 암호화 키 로테이션 정책 수립
3. 리스크 limit 기본값 강제(미설정 시 거래 불가)
4. 타임프레임 매핑 테이블 Binance 사양 동기화
5. 전략 함수 회귀테스트(고정 입력 대비 동일 출력) 자동화
6. 백테스트/실거래 결과 차이 모니터링(슬리피지/지연 원인 분석)

---

## 14. 단계별 구현 로드맵

### Phase 1 (MVP)
- 인증/전략설정/백테스트/결과차트
- 모의거래 세션 + 실시간 PnL
- 리스크 제한(레버리지, 일손실, estop)

### Phase 2
- 실거래 연결, API키 암호화 저장
- 학습 세션 기록/비교 대시보드
- 고급 체결모델/리포팅

### Phase 3
- 멀티심볼 포트폴리오
- 시나리오 기반 스트레스 테스트
- HA(고가용) 및 DR(재해복구) 구성

