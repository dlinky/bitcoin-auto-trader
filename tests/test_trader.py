#!/usr/bin/env python3
"""
Trader 클래스 테스트 코드
실행 방법: python test_trader.py
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.binance_client import BinanceClient
from src.api.supabase_client import SupabaseClient
from src.strategies.macd_atr import MACDATRStrategy
from src.core.trader import Trader
from src.utils.logger import get_logger

logger = get_logger(__name__)

def setup_test_environment():
    """테스트 환경 설정"""
    print("🔧 Trader 테스트 환경 설정 중...")
    
    # .env 파일 로드
    env_path = project_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 환경변수 로드: {env_path}")
    else:
        print(f"❌ .env 파일을 찾을 수 없음: {env_path}")
        return None
    
    try:
        # 클라이언트들 초기화
        binance_client = BinanceClient(
            os.getenv('BINANCE_API_KEY'),
            os.getenv('BINANCE_SECRET_KEY'),
            testnet=True
        )
        
        supabase_client = SupabaseClient()
        
        # 전략 초기화
        strategy = MACDATRStrategy(
            supabase_client=supabase_client,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            atr_period=14
        )
        
        print("✅ 클라이언트 및 전략 초기화 완료")
        return binance_client, supabase_client, strategy
        
    except Exception as e:
        print(f"❌ 환경 설정 실패: {e}")
        return None

def setup_test_trader_in_db(supabase_client):
    """테스트용 트레이더를 DB에 생성"""
    print("\n📝 테스트 트레이더 DB 설정")
    
    try:
        # 기존 테스트 트레이더 삭제 (있다면)
        supabase_client.client.table('traders').delete().eq(
            'name', 'TEST_Trader_BTC'
        ).execute()
        
        # 테스트 트레이더 생성
        trader_data = {
            'name': 'TEST_Trader_BTC',
            'symbol': 'BTCUSDT',
            'strategy_id': 1,  # MACD_ATR_Strategy
            'allocated_budget': 1000.0,
            'investment_amount': 500.0,
            'total_pnl': 0.0,
            'is_active': True
        }
        
        response = supabase_client.client.table('traders').insert(trader_data).execute()
        
        if response.data:
            trader_id = response.data[0]['id']
            print(f"✅ 테스트 트레이더 생성 완료 (ID: {trader_id})")
            return trader_id
        else:
            print("❌ 테스트 트레이더 생성 실패")
            return None
            
    except Exception as e:
        print(f"❌ 테스트 트레이더 DB 설정 실패: {e}")
        return None

def test_trader_initialization():
    """Trader 초기화 테스트"""
    print("\n1️⃣ Trader 초기화 테스트")
    
    # 환경 설정
    result = setup_test_environment()
    if not result:
        print("❌ 환경 설정 실패로 테스트 중단")
        return None
    
    binance_client, supabase_client, strategy = result
    
    # DB에 테스트 트레이더 생성
    trader_id = setup_test_trader_in_db(supabase_client)
    if not trader_id:
        print("❌ 테스트 트레이더 DB 생성 실패")
        return None
    
    try:
        # Trader 초기화
        trader = Trader(
            trader_id=trader_id,
            symbol='BTCUSDT',
            binance_client=binance_client,
            supabase_client=supabase_client,
            strategy=strategy,
            allocated_budget=1000.0,
            investment_ratio=0.5
        )
        
        print("✅ Trader 초기화 성공")
        
        # 상태 확인
        status = trader.get_trader_status()
        print(f"   트레이더 ID: {status['trader_id']}")
        print(f"   거래 심볼: {status['symbol']}")
        print(f"   할당 예산: ${status['allocated_budget']:,.2f}")
        print(f"   투자 금액: ${status['investment_amount']:,.2f}")
        print(f"   활성 상태: {status['is_active']}")
        print(f"   전략: {status['strategy']}")
        
        return trader, binance_client, supabase_client, strategy
        
    except Exception as e:
        print(f"❌ Trader 초기화 실패: {e}")
        return None

def test_position_management(trader):
    """포지션 관리 테스트"""
    print("\n2️⃣ 포지션 관리 테스트")
    
    try:
        # 1. 현재 포지션 확인
        print("📊 현재 포지션 상태 확인")
        trader.update_position_info()
        
        status = trader.get_trader_status()
        print(f"   현재 포지션: {status['current_position']}")
        print(f"   포지션 크기: {status['position_size']}")
        print(f"   진입가: ${status['entry_price']:.4f}")
        print(f"   미실현 손익: ${status['unrealized_pnl']:.2f}")
        
        # 2. 현재 가격 조회 테스트
        current_price = trader.get_current_price()
        if current_price:
            print(f"   현재 가격: ${current_price:,.4f}")
            
            # 3. 주문 수량 계산 테스트
            quantity = trader.calculate_order_quantity(current_price)
            if quantity:
                print(f"   계산된 주문 수량: {quantity:.8f} BTC")
                investment_value = quantity * current_price
                print(f"   투자 금액: ${investment_value:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 포지션 관리 테스트 실패: {e}")
        return False

def test_signal_processing(trader):
    """시그널 처리 테스트"""
    print("\n3️⃣ 시그널 처리 테스트")
    
    try:
        print("📈 Strategy 시그널 생성 및 처리 테스트")
        
        # 현재 포지션 상태 확인
        trader.update_position_info()
        current_position = trader.current_position
        print(f"   현재 포지션: {current_position}")
        
        # 시그널 처리 테스트 (실제 주문은 하지 않음)
        signal_result = trader.check_and_execute_signal()
        
        print(f"   시그널 결과:")
        print(f"      액션: {signal_result.get('action', 'unknown')}")
        print(f"      포지션 변경: {signal_result.get('position_changed', False)}")
        print(f"      사유: {signal_result.get('reason', 'N/A')}")
        
        if 'signal' in signal_result and signal_result['signal']:
            signal = signal_result['signal']
            print(f"      시그널: {signal.get('signal', 'N/A')}")
            print(f"      신뢰도: {signal.get('confidence', 0):.2f}")
            print(f"      시그널 사유: {signal.get('reason', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 시그널 처리 테스트 실패: {e}")
        return False

def test_trading_cycle_dry_run(trader):
    """트레이딩 사이클 드라이런 테스트"""
    print("\n4️⃣ 트레이딩 사이클 드라이런 테스트")
    
    try:
        print("🔄 전체 트레이딩 사이클 실행 (실제 주문 제외)")
        
        # 원래 주문 메서드들을 백업하고 모킹
        original_execute_entry = trader.execute_entry_order
        original_execute_exit = trader.execute_exit_order
        
        def mock_execute_entry(signal):
            print(f"      🟢 [MOCK] 진입 주문: {signal['signal']}")
            return {
                'action': 'entry_mock',
                'signal': signal,
                'position_changed': False,  # 실제로 변경하지 않음
                'reason': 'Mock 테스트 - 실제 주문 안함'
            }
        
        def mock_execute_exit(signal):
            print(f"      🔴 [MOCK] 청산 주문: {signal['signal']}")
            return {
                'action': 'exit_mock',
                'signal': signal,
                'position_changed': False,  # 실제로 변경하지 않음
                'reason': 'Mock 테스트 - 실제 주문 안함'
            }
        
        # 메서드 모킹
        trader.execute_entry_order = mock_execute_entry
        trader.execute_exit_order = mock_execute_exit
        
        # 트레이딩 사이클 실행
        start_time = time.time()
        cycle_result = trader.execute_trading_cycle()
        elapsed_time = time.time() - start_time
        
        # 원래 메서드 복원
        trader.execute_entry_order = original_execute_entry
        trader.execute_exit_order = original_execute_exit
        
        # 결과 출력
        print(f"✅ 트레이딩 사이클 완료 ({elapsed_time:.2f}초)")
        print(f"   성공 여부: {cycle_result['success']}")
        print(f"   심볼: {cycle_result.get('symbol', 'N/A')}")
        
        if 'signal_result' in cycle_result:
            sr = cycle_result['signal_result']
            print(f"   시그널 액션: {sr.get('action', 'N/A')}")
        
        status = trader.get_trader_status()
        print(f"   현재 포지션: {status['current_position']}")
        print(f"   미실현 PnL: ${status['unrealized_pnl']:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 트레이딩 사이클 테스트 실패: {e}")
        return False

def test_database_operations(trader):
    """데이터베이스 연동 테스트"""
    print("\n5️⃣ 데이터베이스 연동 테스트")
    
    try:
        # 1. 트레이더 PnL 업데이트 테스트
        print("💾 PnL 업데이트 테스트")
        trader.update_trader_pnl()
        print("   ✅ PnL 업데이트 완료")
        
        # 2. 포지션 저장 테스트 (현재 상태 기준)
        print("💾 포지션 저장 테스트")
        trader.save_position_to_db()
        print("   ✅ 포지션 저장 완료")
        
        # 3. DB에서 트레이더 정보 확인
        print("📊 DB 트레이더 정보 확인")
        trader_info = trader.db_client.get_trader_info(trader.trader_id)
        
        if trader_info:
            print(f"   트레이더명: {trader_info['name']}")
            print(f"   총 손익: ${float(trader_info['total_pnl']):.2f}")
            print(f"   활성 상태: {trader_info['is_active']}")
            print(f"   마지막 업데이트: {trader_info['updated_at']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 데이터베이스 연동 테스트 실패: {e}")
        return False

def test_trader_controls(trader):
    """트레이더 제어 테스트"""
    print("\n6️⃣ 트레이더 제어 테스트")
    
    try:
        # 1. 트레이딩 정지 테스트
        print("⏸️ 트레이딩 정지 테스트")
        trader.stop_trading("테스트 목적")
        
        status = trader.get_trader_status()
        print(f"   활성 상태: {status['is_active']}")
        
        # 2. 트레이딩 재시작 테스트
        print("▶️ 트레이딩 재시작 테스트")
        trader.resume_trading("테스트 완료")
        
        status = trader.get_trader_status()
        print(f"   활성 상태: {status['is_active']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 트레이더 제어 테스트 실패: {e}")
        return False

def cleanup_test_data(supabase_client, trader_id):
    """테스트 데이터 정리"""
    print("\n🧹 테스트 데이터 정리")
    
    try:
        # 테스트 트레이더 삭제
        supabase_client.client.table('traders').delete().eq(
            'id', trader_id
        ).execute()
        
        print("✅ 테스트 데이터 정리 완료")
        
    except Exception as e:
        print(f"⚠️ 테스트 데이터 정리 중 에러: {e}")

def main():
    """메인 테스트 함수"""
    print("🧪 Trader 클래스 통합 테스트 시작")
    print("=" * 60)
    
    # 1. Trader 초기화 테스트
    result = test_trader_initialization()
    if not result:
        print("\n💥 Trader 초기화 실패로 테스트 중단")
        return
    
    trader, binance_client, supabase_client, strategy = result
    
    # 테스트 결과 추적
    test_results = []
    
    # 2. 포지션 관리 테스트
    result = test_position_management(trader)
    test_results.append(('포지션 관리', result))
    
    # 3. 시그널 처리 테스트
    result = test_signal_processing(trader)
    test_results.append(('시그널 처리', result))
    
    # 4. 트레이딩 사이클 테스트
    result = test_trading_cycle_dry_run(trader)
    test_results.append(('트레이딩 사이클', result))
    
    # 5. 데이터베이스 연동 테스트
    result = test_database_operations(trader)
    test_results.append(('데이터베이스 연동', result))
    
    # 6. 트레이더 제어 테스트
    result = test_trader_controls(trader)
    test_results.append(('트레이더 제어', result))
    
    # 테스트 데이터 정리
    cleanup_test_data(supabase_client, trader.trader_id)
    
    # 최종 결과
    print("\n" + "=" * 60)
    print("🎯 테스트 결과 요약")
    
    success_count = 0
    total_count = len(test_results)
    
    for test_name, success in test_results:
        status = "✅ 통과" if success else "❌ 실패"
        print(f"   {status} {test_name}")
        if success:
            success_count += 1
    
    print(f"\n📊 전체 결과: {success_count}/{total_count}개 테스트 통과")
    
    if success_count == total_count:
        print("\n🎉 모든 테스트 통과! Trader 클래스 준비 완료")
        print("\n📋 다음 단계:")
        print("   1. 실제 주문 테스트 (소액)")
        print("   2. 스케줄러 개발 및 통합")
        print("   3. 전체 시스템 통합 테스트")
    else:
        print(f"\n⚠️ {total_count - success_count}개 테스트 실패")
        print("   문제 해결 후 재테스트 필요")
    
    print("\n💡 참고: 실제 주문은 mock으로 처리되었습니다")
    print("   실제 주문 테스트는 소액으로 별도 진행하세요")

if __name__ == "__main__":
    main()