# 암호화폐 자동매매 프로그램

# 📋 목차
- [프로젝트 개요](#프로젝트-개요)
- [설치 및 설정](#설치-및-설정)
- [모듈별 문서](#모듈별-문서)
    - [BinanceClient](#binanceclient)
    - [Strategy](#Strategy)
    - [Trader](#Trader)
    - [DataCollector](#DataCollector)
    - [Scheduler](#Scheduler)
    - [RiskManager](#RiskManager)
    - [TradingSystem](#TradingSystem)
    - [SlackBot](#SlackBot)
    - [Logger](#Logger)
---

# 프로젝트 개요
## 핵심 기능
- 바이낸스 선물시장에서 암호화폐 24시간 자동매매
- 트레이더 객체를 통해 전략, 티커를 선택하여 독립적 운영
- 웹 대시보드로 손익현황 확인
- 슬랙 챗봇으로 문제상황 알림
## 개발 환경 구성
- 로컬 개발 : MacOS 15.5 Sequoia + VSCode
- 운영 서버 : Ubuntu Server 24.04
- 연결 방식 : VSCode + SSH Remote
## 기술 스택
- 언어 : Python 3.12.3
- 패키지 관리 : uv &rarr; Docker
- 핵심 로직 : Python (API, 지표 계산)
- WebUI : Next.js
- DB : Supabase (PostgreSQL)
- 모니터링 : Slack Bot
## 외부 서비스
- Binance Futures API (테스트넷 지원)
- Supabase
- Slack Bot

# 설치 및 설정
```bash
uv add pandas python-binance python-dotenv supabase
uv add slack-sdk schedule loguru numpy ta-lib
```
# 모듈별 문서
## BinanceClient
바이낸스 선물 거래를 위한 API 클라이언트 모듈
## 📁 파일 위치
```
src/api/binance_client.py
```
## 🚀 주요 기능
- **OHLCV 데이터 조회**: 캔들스틱 데이터를 pandas DataFrame으로 반환
- **포지션 관리**: 현재 포지션 정보 조회 및 상태 확인
- **주문 실행**: 시장가 매수/매도 주문
- **계좌 조회**: USDT 잔고 및 사용 가능 금액 확인
- **심볼 정보**: 최소 주문 단위 등 거래 규칙 조회
- **수량 계산**: USDT 금액 기준 주문 수량 자동 계산
## ⚙️ 설정 요구사항
### 환경변수 (config/.env)
```env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret_key
BINANCE_TESTNET=true
```
## 💻 사용 방법
### 기본 초기화
```python
from src.api.binance_client import BinanceClient

client = BinanceClient(
    api_key="your_api_key",
    secret_key="your_secret_key",
    testnet=True
)
```
### 주요 메서드 사용 예시
#### 1. 캔들 데이터 조회
```python
df = client.get_klines('BTCUSDT', '1m', 100)
print(df.tail())
```
#### 2. 포지션 확인
```python
position = client.get_position_info('BTCUSDT')
print(f"포지션: {position['side']} {position['size']}")
```
#### 3. 주문 실행
```python
current_price = df.iloc[-1]['close']
quantity = client.calculate_quentity('BTCUSDT', 50, current_price)
order = client.place_market_order('BTCUSDT', 'BUY', quantity)
```
#### 4. 계좌 잔고 확인
```python
balance = client.get_account_balance()
print(f"사용 가능: {balance['available']} USDT")
```
## 🛡️ 에러 처리
- 재시도 로직: API 실패 시 1회 자동 재시도
- 타임아웃: 5초
- 로깅: 모든 API 호출 및 에러 로그 기록
## 🧪 테스트
### 테스트 실행
```bash
python test_binance_client.py
```
### 테스트 내용
- ✅ API 연결 확인
- ✅ 계좌 잔고 조회
- ✅ 심볼 정보 조회
- ✅ 캔들 데이터 수집
- ✅ 포지션 정보 확인
- ✅ 주문 수량 계산
- ✅ 에러 처리 동작
## ⚠️ 주의사항
- 테스트넷 사용 권장
- 바이낸스 API Rate Limit 준수
- API 키는 환경변수로 관리하며, .env 파일을 Git에 커밋하지 않도록 주의
## 🔗 연동 객체
- Trader: 포지션 관리 및 주문 실행
- DataCollector: OHLCV 데이터 수집
- RiskManager: 주문 전 리스크 검증
- SlackBot: 거래 알림 전송
## 📈 데이터 형식
### 캔들 데이터 (DataFrame)
```python
   timestamp              open     high     low      close     volume
0  2025-01-01 00:00:00    95000.0  95100.0  94900.0  95050.0   1234.56
```
### 포지션 정보 (Dict)
```python
{
    'symbol': 'BTCUSDT',
    'size': 0.001,           # 포지션 크기
    'entry_price': 95000.0,  # 진입가
    'unrealized_pnl': 10.5,  # 미실현 손익
    'side': 'LONG'           # LONG/SHORT/NONE
}
```
### 주문 결과 (Dict)
```python
{
    'order_id': 123456789,
    'symbol': 'BTCUSDT',
    'side': 'BUY',
    'quantity': 0.001,
    'price': 95000.0,
    'status': 'FILLED',
    'time': pd.Timestamp('2025-01-01 00:00:00')
}