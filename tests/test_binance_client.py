#!/usr/bin/env python3
"""
BinanceClient 테스트 코드
실행 방법: python test_binance_client.py
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.binance_client import BinanceClient

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_binance_client():
    """BinanceClient 기능 테스트"""
    
    # .env 파일 로드 (config 폴더에서)
    # 현재 파일이 프로젝트 루트에 있으므로
    project_root = os.path.dirname(os.path.abspath(__file__))  # 프로젝트 루트
    env_path = os.path.join(project_root, 'config', '.env')
    
    print(f"📄 .env 파일 경로: {env_path}")
    
    if not os.path.exists(env_path):
        print(f"❌ .env 파일을 찾을 수 없습니다: {env_path}")
        return False
        
    load_dotenv(env_path)
    
    # 환경변수에서 API 키 로드
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    if not testnet:
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_API_SECRET')
    else:
        api_key = os.getenv('TESTNET_API_KEY')
        secret_key = os.getenv('TESTNET_API_SECRET')
    
    print(f"api_key = {api_key}")
    print(f"api_secret = {secret_key}")
    
    if not api_key or not secret_key:
        print("❌ BINANCE_API_KEY 또는 BINANCE_SECRET_KEY가 .env 파일에 설정되지 않았습니다")
        return False
    
    try:
        print("🚀 BinanceClient 테스트 시작")
        print(f"📊 테스트넷 모드: {testnet}")
        print("-" * 50)
        
        # 클라이언트 초기화
        client = BinanceClient(api_key, secret_key, testnet)
        print("✅ BinanceClient 초기화 성공")
        
        # 1. 계좌 잔고 조회 테스트
        print("\n1️⃣ 계좌 잔고 조회 테스트")
        balance = client.get_account_balance()
        print(f"   USDT 잔고: {balance['available']:.2f} USDT")
        
        # 2. 심볼 정보 조회 테스트
        print("\n2️⃣ 심볼 정보 조회 테스트")
        symbol_info = client.get_symbol_info('BTCUSDT')
        print(f"   심볼: {symbol_info['symbol']}")
        print(f"   최소 수량: {symbol_info['min_qty']}")
        print(f"   수량 단위: {symbol_info['step_size']}")
        print(f"   상태: {symbol_info['status']}")
        
        # 3. 캔들 데이터 조회 테스트
        print("\n3️⃣ 캔들 데이터 조회 테스트")
        klines = client.get_klines('BTCUSDT', '1m', 10)
        print(f"   조회된 캔들 수: {len(klines)}")
        print(f"   최신 캔들 시간: {klines.iloc[-1]['timestamp']}")
        print(f"   최신 종가: ${klines.iloc[-1]['close']:.2f}")
        
        # 4. 포지션 정보 조회 테스트
        print("\n4️⃣ 포지션 정보 조회 테스트")
        position = client.get_position_info('BTCUSDT')
        print(f"   포지션 크기: {position['size']}")
        print(f"   포지션 방향: {position['side']}")
        print(f"   미실현 손익: {position['unrealized_pnl']:.2f} USDT")
        
        # 5. 주문 수량 계산 테스트
        print("\n5️⃣ 주문 수량 계산 테스트")
        try:
            current_price = klines.iloc[-1]['close']
            test_usdt = 50  # 50 USDT로 테스트
            quantity = client.calculate_quantity('BTCUSDT', test_usdt, current_price)
            print(f"   {test_usdt} USDT @ ${current_price:.2f} = {quantity} BTC")
        except Exception as e:
            print(f"   ⚠️ 주문 수량 계산 실패: {e}")
        
        # 주의사항 출력
        print("\n" + "=" * 50)
        print("⚠️  주의사항:")
        print("   - 실제 주문 테스트는 포함되지 않았습니다")
        print("   - 테스트넷에서도 신중하게 진행하세요")
        print("   - 모든 기능이 정상 동작하면 다음 단계로 진행 가능합니다")
        
        return True
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        return False

def test_error_handling():
    """에러 처리 테스트"""
    print("\n🔧 에러 처리 테스트")
    
    # 잘못된 API 키로 테스트
    try:
        client = BinanceClient("invalid_key", "invalid_secret", True)
        client.get_account_balance()
        print("❌ 에러 처리 테스트 실패 - 예외가 발생하지 않음")
    except Exception as e:
        print(f"✅ 에러 처리 정상 동작: {type(e).__name__}")

if __name__ == "__main__":
    print("🔍 BinanceClient 통합 테스트")
    print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 메인 테스트 실행
    success = test_binance_client()
    
    # 에러 처리 테스트
    test_error_handling()
    
    if success:
        print("\n🎉 모든 테스트 통과!")
        print("   다음 단계: Strategy 클래스 개발")
    else:
        print("\n💥 테스트 실패")
        print("   .env 파일과 API 키를 확인하세요")