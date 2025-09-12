#!/usr/bin/env python3
"""
TradingScheduler 테스트 코드
실행 방법: python test_scheduler.py
"""

import os
import sys
import time
import threading
from pathlib import Path
from unittest.mock import Mock, MagicMock
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.api.binance_client import BinanceClient
from src.api.supabase_client import SupabaseClient
from src.strategies.macd_atr import MACDATRStrategy
from src.core.trader import Trader
from src.core.data_collector import DataCollector
from src.core.scheduler import TradingScheduler, SlackBot
from src.utils.logger import get_logger

logger = get_logger(__name__)

def setup_test_environment():
    """테스트 환경 설정"""
    print("🔧 Scheduler 테스트 환경 설정 중...")
    
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
        
        # 데이터 수집기 초기화
        data_collector = DataCollector(
            binance_client=binance_client,
            supabase_client=supabase_client,
            symbols=['BTCUSDT']
        )
        
        # 전략 초기화
        strategy = MACDATRStrategy(
            supabase_client=supabase_client
        )
        
        print("✅ 모든 컴포넌트 초기화 완료")
        return binance_client, supabase_client, data_collector, strategy
        
    except Exception as e:
        print(f"❌ 환경 설정 실패: {e}")
        return None

def create_mock_trader(trader_id: int, symbol: str):
    """테스트용 Mock Trader 생성"""
    mock_trader = Mock()
    mock_trader.trader_id = trader_id
    mock_trader.symbol = symbol
    mock_trader.is_active = True
    
    # execute_trading_cycle 메서드 모킹
    def mock_execute_trading_cycle():
        time.sleep(0.1)  # 실제 처리 시간 시뮬레이션
        return {
            'success': True,
            'symbol': symbol,
            'signal_result': {
                'action': 'hold',
                'signal': {'signal': 'HOLD', 'confidence': 0.0},
                'position_changed': False
            },
            'current_position': None,
            'unrealized_pnl': 0.0,
            'elapsed_time': 0.1
        }
    
    mock_trader.execute_trading_cycle = mock_execute_trading_cycle
    
    # get_trader_status 메서드 모킹
    def mock_get_trader_status():
        return {
            'trader_id': trader_id,
            'symbol': symbol,
            'is_active': True,
            'allocated_budget': 1000.0,
            'investment_amount': 500.0,
            'current_position': None,
            'position_size': 0.0,
            'entry_price': 0.0,
            'unrealized_pnl': 0.0,
            'strategy': 'MACD_ATR_Strategy'
        }
    
    mock_trader.get_trader_status = mock_get_trader_status
    
    return mock_trader

def test_scheduler_initialization():
    """Scheduler 초기화 테스트"""
    print("\n1️⃣ Scheduler 초기화 테스트")
    
    # 환경 설정
    result = setup_test_environment()
    if not result:
        print("❌ 환경 설정 실패로 테스트 중단")
        return None
    
    binance_client, supabase_client, data_collector, strategy = result
    
    try:
        # Mock 트레이더 생성
        mock_traders = [
            create_mock_trader(1, 'BTCUSDT'),
            create_mock_trader(2, 'ETHUSDT')
        ]
        
        # Mock SlackBot 생성
        mock_slack_bot = Mock()
        mock_slack_bot.send_message = Mock(return_value=True)
        
        # Scheduler 초기화
        scheduler = TradingScheduler(
            data_collector=data_collector,
            traders=mock_traders,
            slack_bot=mock_slack_bot
        )
        
        print("✅ Scheduler 초기화 성공")
        
        # 상태 확인
        status = scheduler.get_scheduler_status()
        print(f"   실행 상태: {status['is_running']}")
        print(f"   총 트레이더: {status['total_traders']}개")
        print(f"   활성 트레이더: {status['active_traders']}개")
        print(f"   총 사이클: {status['total_cycles']}회")
        
        return scheduler, data_collector, mock_traders, mock_slack_bot
        
    except Exception as e:
        print(f"❌ Scheduler 초기화 실패: {e}")
        return None

def test_manual_cycle_execution(scheduler):
    """수동 사이클 실행 테스트"""
    print("\n2️⃣ 수동 사이클 실행 테스트")
    
    try:
        print("🔄 수동으로 트레이딩 사이클 실행")
        
        # 실행 전 상태
        status_before = scheduler.get_scheduler_status()
        print(f"   실행 전 총 사이클: {status_before['total_cycles']}회")
        
        # 스케줄러 상태를 실행 중으로 변경 (임시)
        scheduler.is_running = True
        
        # 수동 실행
        start_time = time.time()
        scheduler.force_execute_cycle()
        execution_time = time.time() - start_time
        
        # 상태 복원
        scheduler.is_running = False
        
        # 실행 후 상태
        status_after = scheduler.get_scheduler_status()
        print(f"   실행 후 총 사이클: {status_after['total_cycles']}회")
        print(f"   실행 시간: {execution_time:.2f}초")
        print(f"   성공률: {status_after['success_rate']:.1f}%")
        
        # 사이클이 증가했는지 확인
        if status_after['total_cycles'] > status_before['total_cycles']:
            print("   ✅ 수동 사이클 실행 성공")
            return True
        else:
            print("   ❌ 사이클 카운터가 증가하지 않음")
            return False
            
    except Exception as e:
        print(f"❌ 수동 사이클 실행 실패: {e}")
        return False

def test_scheduler_start_stop(scheduler):
    """Scheduler 시작/정지 테스트"""
    print("\n3️⃣ Scheduler 시작/정지 테스트")
    
    try:
        # 시작 테스트
        print("▶️ Scheduler 시작 테스트")
        
        initial_status = scheduler.get_scheduler_status()
        print(f"   초기 실행 상태: {initial_status['is_running']}")
        
        scheduler.start()
        time.sleep(2)  # 스케줄러가 시작될 시간 대기
        
        started_status = scheduler.get_scheduler_status()
        print(f"   시작 후 실행 상태: {started_status['is_running']}")
        
        if started_status['is_running']:
            print("   ✅ Scheduler 시작 성공")
        else:
            print("   ❌ Scheduler 시작 실패")
            return False
        
        # 정지 테스트
        print("⏹️ Scheduler 정지 테스트")
        
        scheduler.stop()
        time.sleep(1)  # 정지될 시간 대기
        
        stopped_status = scheduler.get_scheduler_status()
        print(f"   정지 후 실행 상태: {stopped_status['is_running']}")
        
        if not stopped_status['is_running']:
            print("   ✅ Scheduler 정지 성공")
            return True
        else:
            print("   ❌ Scheduler 정지 실패")
            return False
            
    except Exception as e:
        print(f"❌ Scheduler 시작/정지 테스트 실패: {e}")
        return False

def test_slack_notifications(scheduler, mock_slack_bot):
    """Slack 알림 테스트"""
    print("\n4️⃣ Slack 알림 테스트")
    
    try:
        print("📱 Slack 알림 기능 테스트")
        
        # Mock 트레이더에서 거래 신호 생성
        mock_trader = scheduler.traders[0]
        
        # 진입 신호 테스트
        entry_signal_result = {
            'action': 'entry',
            'direction': 'LONG',
            'quantity': 0.001,
            'price': 50000.0,
            'signal': {'signal': 'ENTRY_LONG', 'confidence': 0.8}
        }
        
        print("   🟢 진입 신호 알림 테스트")
        scheduler._send_trading_notification(mock_trader, entry_signal_result)
        
        # 청산 신호 테스트
        exit_signal_result = {
            'action': 'exit',
            'direction': 'LONG',
            'quantity': 0.001,
            'entry_price': 50000.0,
            'exit_price': 51000.0,
            'realized_pnl': 10.0,
            'signal': {'signal': 'EXIT_LONG', 'confidence': 0.7}
        }
        
        print("   🔴 청산 신호 알림 테스트")
        scheduler._send_trading_notification(mock_trader, exit_signal_result)
        
        # 상태 리포트 테스트
        print("   📊 상태 리포트 알림 테스트")
        scheduler._send_status_report()
        
        # Mock이 호출되었는지 확인
        if mock_slack_bot.send_message.called:
            print(f"   ✅ Slack 메시지 전송 호출됨 ({mock_slack_bot.send_message.call_count}번)")
            return True
        else:
            print("   ❌ Slack 메시지 전송이 호출되지 않음")
            return False
            
    except Exception as e:
        print(f"❌ Slack 알림 테스트 실패: {e}")
        return False

def test_scheduler_timing(scheduler):
    """Scheduler 타이밍 테스트"""
    print("\n5️⃣ Scheduler 타이밍 테스트")
    
    try:
        print("⏰ 실행 타이밍 및 성능 테스트")
        
        # 여러 번 수동 실행하여 성능 측정
        execution_times = []
        
        for i in range(3):
            start_time = time.time()
            scheduler.force_execute_cycle()
            execution_time = time.time() - start_time
            execution_times.append(execution_time)
            
            print(f"   실행 {i+1}: {execution_time:.2f}초")
        
        avg_time = sum(execution_times) / len(execution_times)
        max_time = max(execution_times)
        
        print(f"   평균 실행 시간: {avg_time:.2f}초")
        print(f"   최대 실행 시간: {max_time:.2f}초")
        
        # 10초 제한 확인
        if max_time < 10.0:
            print("   ✅ 10초 제한 내에서 실행 완료")
            return True
        else:
            print("   ⚠️ 10초 제한 초과 - 최적화 필요")
            return False
            
    except Exception as e:
        print(f"❌ 타이밍 테스트 실패: {e}")
        return False

def test_error_handling(scheduler):
    """에러 처리 테스트"""
    print("\n6️⃣ 에러 처리 테스트")
    
    try:
        print("💥 에러 상황 처리 테스트")
        
        # 트레이더에서 에러 발생 시뮬레이션
        original_execute = scheduler.traders[0].execute_trading_cycle
        
        def error_execute():
            raise Exception("테스트용 에러")
        
        # 스케줄러를 실행 상태로 설정
        scheduler.is_running = True
        
        scheduler.traders[0].execute_trading_cycle = error_execute
        
        # 에러가 있어도 스케줄러는 계속 실행되어야 함
        status_before = scheduler.get_scheduler_status()
        
        scheduler.force_execute_cycle()  # 에러 발생 예상
        
        status_after = scheduler.get_scheduler_status()
        
        # 원래 함수 복원
        scheduler.traders[0].execute_trading_cycle = original_execute
        
        # 사이클은 증가했지만 실패로 기록되어야 함
        if status_after['total_cycles'] > status_before['total_cycles']:
            print("   ✅ 에러 발생해도 스케줄러 계속 실행")
            
            if status_after['failed_cycles'] > status_before['failed_cycles']:
                print("   ✅ 실패 통계 정상 기록")
                return True
            else:
                print("   ❌ 실패 통계 기록 안됨")
                return False
        else:
            print("   ❌ 에러로 인해 스케줄러 정지됨")
            return False
            
    except Exception as e:
        print(f"❌ 에러 처리 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 함수"""
    print("🧪 TradingScheduler 통합 테스트 시작")
    print("=" * 60)
    
    # 1. Scheduler 초기화 테스트
    result = test_scheduler_initialization()
    if not result:
        print("\n💥 Scheduler 초기화 실패로 테스트 중단")
        return
    
    scheduler, data_collector, mock_traders, mock_slack_bot = result
    
    # 테스트 결과 추적
    test_results = []
    
    # 2. 수동 사이클 실행 테스트
    result = test_manual_cycle_execution(scheduler)
    test_results.append(('수동 사이클 실행', result))
    
    # 3. 시작/정지 테스트
    result = test_scheduler_start_stop(scheduler)
    test_results.append(('시작/정지 제어', result))
    
    # 4. Slack 알림 테스트
    result = test_slack_notifications(scheduler, mock_slack_bot)
    test_results.append(('Slack 알림', result))
    
    # 5. 타이밍 테스트
    result = test_scheduler_timing(scheduler)
    test_results.append(('실행 타이밍', result))
    
    # 6. 에러 처리 테스트
    result = test_error_handling(scheduler)
    test_results.append(('에러 처리', result))
    
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
    
    # 최종 상태 출력
    final_status = scheduler.get_scheduler_status()
    print(f"\n📈 최종 스케줄러 상태:")
    print(f"   총 실행 사이클: {final_status['total_cycles']}회")
    print(f"   성공률: {final_status['success_rate']:.1f}%")
    print(f"   활성 트레이더: {final_status['active_traders']}/{final_status['total_traders']}개")
    
    if success_count == total_count:
        print("\n🎉 모든 테스트 통과! TradingScheduler 준비 완료")
        print("\n📋 다음 단계:")
        print("   1. 전체 시스템 통합 테스트")
        print("   2. 실제 환경에서 소액 테스트")
        print("   3. 24시간 가동 시험 운영")
    else:
        print(f"\n⚠️ {total_count - success_count}개 테스트 실패")
        print("   문제 해결 후 재테스트 필요")
    
    print("\n💡 참고: Mock 트레이더로 안전하게 테스트되었습니다")

if __name__ == "__main__":
    main()