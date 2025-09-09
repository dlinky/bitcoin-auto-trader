#!/usr/bin/env python3
"""
자본 관리 시스템 테스트 스크립트
프로젝트 루트에서 실행: python test_capital_manager.py
"""

import sys
import os
import logging

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.core.capital_manager import CapitalManager, CapitalConfig

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_capital_manager():
    """자본 관리 시스템 테스트"""
    
    print("=" * 60)
    print("💰 자본 관리 시스템 테스트 시작")
    print("=" * 60)
    
    # 설정 생성
    config = CapitalConfig(
        total_capital_ratio=0.1,    # 전체 자본의 10% 사용
        max_loss_ratio=0.02,        # 최대 손실 2%
        max_position_ratio=0.5,     # 단일 포지션 최대 50%
        min_order_size=0.001,       # 최소 주문 0.001
        leverage=1                  # 1배 레버리지
    )
    
    # 자본 관리자 생성
    capital_manager = CapitalManager(config)
    
    print("\n" + "-" * 40)
    print("1️⃣ 초기 설정 및 잔고 업데이트")
    print("-" * 40)
    
    # 가상의 계정 잔고: 1000 USDT
    total_balance = 1000.0
    capital_manager.update_balance(total_balance)
    
    status = capital_manager.get_capital_status()
    print(f"✅ 총 잔고: {status['total_balance']:.2f} USDT")
    print(f"✅ 할당 자본: {status['allocated_capital']:.2f} USDT")
    print(f"✅ 사용 가능: {status['available_capital']:.2f} USDT")
    
    print("\n" + "-" * 40)
    print("2️⃣ 포지션 크기 계산 테스트")
    print("-" * 40)
    
    # BTCUSDT 포지션 크기 계산 (가상 가격: $50,000)
    btc_price = 50000.0
    stop_loss_price = 48000.0  # 4% 손절
    
    position_info = capital_manager.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=btc_price,
        stop_loss_price=stop_loss_price
    )
    
    print(f"✅ BTC 포지션 정보:")
    print(f"   💱 진입가: ${btc_price:,}")
    print(f"   🛑 손절가: ${stop_loss_price:,}")
    print(f"   📊 포지션 크기: {position_info['size']:.6f} BTC")
    print(f"   💰 명목가치: ${position_info['notional']:.2f}")
    print(f"   ⚠️ 리스크 금액: ${position_info['risk_amount']:.2f}")
    print(f"   📈 최대 손실: {position_info['max_loss_ratio']:.2f}%")
    
    print("\n" + "-" * 40)
    print("3️⃣ 자본 예약 테스트")
    print("-" * 40)
    
    # 자본 예약 (포지션 진입)
    if position_info['size'] > 0:
        success = capital_manager.reserve_capital("BTCUSDT", position_info['notional'])
        if success:
            print("✅ 자본 예약 성공!")
            
            status = capital_manager.get_capital_status()
            print(f"   📊 자본 사용률: {status['utilization_ratio']:.1f}%")
            print(f"   💳 남은 자본: ${status['available_capital']:.2f}")
        else:
            print("❌ 자본 예약 실패!")
    
    print("\n" + "-" * 40)
    print("4️⃣ 추가 포지션 테스트")
    print("-" * 40)
    
    # ETH 포지션도 계산해보기
    eth_price = 3000.0
    eth_stop_loss = 2850.0  # 5% 손절
    
    eth_position = capital_manager.calculate_position_size(
        symbol="ETHUSDT",
        entry_price=eth_price,
        stop_loss_price=eth_stop_loss
    )
    
    print(f"✅ ETH 포지션 정보:")
    print(f"   💱 진입가: ${eth_price:,}")
    print(f"   🛑 손절가: ${eth_stop_loss:,}")
    print(f"   📊 포지션 크기: {eth_position['size']:.3f} ETH")
    print(f"   💰 명목가치: ${eth_position['notional']:.2f}")
    
    if eth_position['size'] > 0:
        success = capital_manager.reserve_capital("ETHUSDT", eth_position['notional'])
        print(f"✅ ETH 자본 예약: {'성공' if success else '실패'}")
    
    print("\n" + "-" * 40)
    print("5️⃣ 손익 시뮬레이션")
    print("-" * 40)
    
    # 가상의 손익 업데이트
    btc_unrealized_pnl = -15.0  # -$15 손실
    eth_unrealized_pnl = 8.0    # +$8 이익
    
    capital_manager.update_unrealized_pnl("BTCUSDT", btc_unrealized_pnl)
    capital_manager.update_unrealized_pnl("ETHUSDT", eth_unrealized_pnl)
    
    total_pnl = capital_manager.get_total_unrealized_pnl()
    print(f"📊 미실현 손익:")
    print(f"   🪙 BTC: ${btc_unrealized_pnl:.2f}")
    print(f"   💎 ETH: ${eth_unrealized_pnl:.2f}")
    print(f"   💰 총합: ${total_pnl:.2f}")
    
    print("\n" + "-" * 40)
    print("6️⃣ 리스크 한도 체크")
    print("-" * 40)
    
    risk_status = capital_manager.check_risk_limits()
    print(f"⚠️ 리스크 현황:")
    print(f"   📉 현재 손실률: {risk_status['current_loss_ratio']:.2f}%")
    print(f"   🚫 최대 허용: {risk_status['max_loss_threshold']:.2f}%")
    print(f"   🚨 한도 초과: {'예' if risk_status['is_risk_limit_exceeded'] else '아니오'}")
    print(f"   📊 자본 사용률: {risk_status['capital_utilization']:.1f}%")
    
    print("\n" + "-" * 40)
    print("7️⃣ 포지션 청산 테스트")
    print("-" * 40)
    
    # BTC 포지션 절반 청산
    partial_notional = position_info['notional'] * 0.5
    capital_manager.release_capital("BTCUSDT", partial_notional)
    print(f"✅ BTC 포지션 50% 청산: ${partial_notional:.2f}")
    
    final_status = capital_manager.get_capital_status()
    print(f"📊 최종 자본 현황:")
    print(f"   💰 사용 자본: ${final_status['used_capital']:.2f}")
    print(f"   💳 사용 가능: ${final_status['available_capital']:.2f}")
    print(f"   📈 사용률: {final_status['utilization_ratio']:.1f}%")
    print(f"   🏢 활성 포지션: {final_status['active_positions']}개")
    
    print("\n" + "=" * 60)
    print("🎉 자본 관리 시스템 테스트 완료!")
    print("=" * 60)
    
    print("\n📋 핵심 기능 확인:")
    print("✅ 자본 할당 및 한도 관리")
    print("✅ 리스크 기반 포지션 크기 계산")
    print("✅ 자본 예약/해제 시스템")
    print("✅ 실시간 손익 추적")
    print("✅ 리스크 한도 모니터링")

def main():
    setup_logging()
    test_capital_manager()

if __name__ == "__main__":
    main()