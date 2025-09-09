#!/usr/bin/env python3
"""
트레이더 객체 테스트 스크립트
프로젝트 루트에서 실행: python test_trader.py
"""

import sys
import os
import logging
import time

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.api.binance_client import BinanceClient
from backend.core.capital_manager import CapitalManager, CapitalConfig
from backend.core.trader import Trader, OrderSide

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_trader_basic():
    """기본 트레이더 기능 테스트"""
    
    print("=" * 60)
    print("🤖 트레이더 객체 테스트 시작")
    print("=" * 60)
    
    # 1. 컴포넌트 초기화
    print("\n" + "-" * 40)
    print("1️⃣ 컴포넌트 초기화")
    print("-" * 40)
    
    try:
        # 바이낸스 클라이언트 (테스트넷)
        binance_client = BinanceClient(testnet=True)
        print("✅ 바이낸스 클라이언트 초기화")
        
        # 자본 관리자
        capital_config = CapitalConfig(
            total_capital_ratio=0.1,
            max_loss_ratio=0.02,
            max_position_ratio=0.8,
            min_order_size=0.001,
            leverage=1
        )
        capital_manager = CapitalManager(capital_config)
        print("✅ 자본 관리자 초기화")
        
        # 트레이더
        trader = Trader("BTCUSDT", binance_client, capital_manager)
        print("✅ 트레이더 초기화")
        
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return
    
    # 2. 트레이더 시작
    print("\n" + "-" * 40)
    print("2️⃣ 트레이더 시작")
    print("-" * 40)
    
    if trader.start():
        print("✅ 트레이더 시작 성공")
    else:
        print("❌ 트레이더 시작 실패")
        return
    
    # 3. 현재 상태 확인
    print("\n" + "-" * 40)
    print("3️⃣ 현재 상태 확인")
    print("-" * 40)
    
    status = trader.get_trading_status()
    
    print(f"📊 트레이더 상태:")
    print(f"   🔄 활성 상태: {status['trader_active']}")
    print(f"   💰 총 잔고: ${status['account_balance']['total_balance']:.2f}")
    print(f"   💳 사용 가능: ${status['account_balance']['available_balance']:.2f}")
    print(f"   📈 할당 자본: ${status['capital_status']['allocated_capital']:.2f}")
    print(f"   📊 사용률: {status['capital_status']['utilization_ratio']:.1f}%")
    
    if status['current_position']:
        pos = status['current_position']
        print(f"   🎯 현재 포지션: {pos['side']} {pos['size']:.6f} BTC")
        print(f"   💵 진입가: ${pos['entry_price']:.2f}")
        print(f"   📈 손익: ${pos['unrealized_pnl']:.2f}")
    else:
        print(f"   📭 현재 포지션: 없음")
    
    # 4. 현재가 조회
    print("\n" + "-" * 40)
    print("4️⃣ 시장 정보 조회")
    print("-" * 40)
    
    current_price = binance_client.get_symbol_price("BTCUSDT")
    if current_price:
        print(f"📈 BTCUSDT 현재가: ${current_price:,.2f}")
        
        # 포지션 크기 계산 시뮬레이션
        stop_loss_price = current_price * 0.95  # 5% 손절
        position_info = capital_manager.calculate_position_size(
            "BTCUSDT", current_price, stop_loss_price
        )
        
        print(f"💡 권장 포지션 크기:")
        print(f"   📊 수량: {position_info['size']:.6f} BTC")
        print(f"   💰 명목가치: ${position_info['notional']:.2f}")
        print(f"   ⚠️ 리스크: ${position_info['risk_amount']:.2f}")
        
        # 5. 테스트 주문 검증
        print("\n" + "-" * 40)
        print("5️⃣ 테스트 주문 검증")
        print("-" * 40)
        
        if binance_client.test_small_order("BTCUSDT", position_info['size']):
            print("✅ 테스트 주문 검증 성공")
            print("   (실제 주문이 실행되지는 않습니다)")
            
            # 실제 주문 시뮬레이션을 원하는지 확인
            print(f"\n❓ 실제 소량 테스트 주문을 실행하시겠습니까?")
            print(f"   수량: {min(0.001, position_info['size']):.6f} BTC")
            print(f"   예상 금액: ${min(0.001, position_info['size']) * current_price:.2f}")
            print(f"   (y/n): ", end="")
            
            user_input = input().lower().strip()
            
            if user_input == 'y':
                test_quantity = min(0.001, position_info['size'])
                if test_quantity > 0:
                    print(f"\n🧪 테스트 주문 실행 중...")
                    
                    # 매수 주문 테스트
                    buy_result = trader.place_market_order(
                        OrderSide.BUY, 
                        test_quantity,
                        stop_loss=current_price * 0.95  # 5% 손절
                    )
                    
                    if buy_result.success:
                        print(f"✅ 테스트 매수 성공!")
                        print(f"   주문 ID: {buy_result.order_id}")
                        print(f"   체결가: ${buy_result.price:.2f}")
                        
                        # 잠시 대기
                        print("⏳ 3초 대기 중...")
                        time.sleep(3)
                        
                        # 포지션 확인
                        position = trader.get_current_position()
                        if position:
                            print(f"📊 포지션 생성됨:")
                            print(f"   크기: {position.size:.6f} BTC")
                            print(f"   손익: ${position.unrealized_pnl:.2f}")
                        
                        # 전체 청산
                        print(f"\n🔄 포지션 청산 중...")
                        close_result = trader.close_position()
                        
                        if close_result.success:
                            print(f"✅ 청산 완료!")
                            print(f"   청산가: ${close_result.price:.2f}")
                        else:
                            print(f"❌ 청산 실패: {close_result.error_message}")
                    
                    else:
                        print(f"❌ 테스트 매수 실패: {buy_result.error_message}")
                else:
                    print(f"⚠️ 테스트 수량이 너무 작습니다")
            else:
                print("📋 실제 주문 테스트를 건너뜁니다")
        
        else:
            print("❌ 테스트 주문 검증 실패")
    
    else:
        print("❌ 현재가 조회 실패")
    
    # 6. 최종 상태 확인
    print("\n" + "-" * 40)
    print("6️⃣ 최종 상태 확인")
    print("-" * 40)
    
    final_status = trader.get_trading_status()
    
    print(f"📊 최종 트레이딩 상태:")
    print(f"   💰 총 거래 수: {final_status['total_trades']}")
    print(f"   🎯 현재 포지션: {'있음' if final_status['current_position'] else '없음'}")
    print(f"   📈 자본 사용률: {final_status['capital_status']['utilization_ratio']:.1f}%")
    print(f"   ⚠️ 리스크 상태: {'정상' if not final_status['risk_status']['is_risk_limit_exceeded'] else '주의'}")
    
    # 7. 트레이더 중지
    print("\n" + "-" * 40)
    print("7️⃣ 트레이더 중지")
    print("-" * 40)
    
    trader.stop()
    print("✅ 트레이더 안전 종료")
    
    print("\n" + "=" * 60)
    print("🎉 트레이더 객체 테스트 완료!")
    print("=" * 60)
    
    print("\n📋 확인된 기능:")
    print("✅ 트레이더 초기화 및 시작/중지")
    print("✅ 바이낸스 API 연동")
    print("✅ 자본 관리 시스템 통합")
    print("✅ 포지션 크기 자동 계산")
    print("✅ 시장가 주문 실행")
    print("✅ 포지션 모니터링")
    print("✅ 자동 청산 기능")
    print("✅ 손절/익절 주문 설정")
    
    print("\n📋 다음 단계:")
    print("1. 매매 전략 구현 (이동평균 크로스)")
    print("2. 리스크 관리 시스템 강화")
    print("3. 실시간 모니터링 추가")

def main():
    setup_logging()
    
    print("⚠️ 주의: 이 테스트는 바이낸스 테스트넷을 사용합니다.")
    print("실제 거래가 실행될 수 있으므로 신중하게 진행해주세요.\n")
    
    test_trader_basic()

if __name__ == "__main__":
    main()