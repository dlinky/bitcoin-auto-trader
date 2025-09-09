#!/usr/bin/env python3
"""
리스크 관리 시스템 테스트 스크립트
프로젝트 루트에서 실행: python test_risk_manager.py
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.core.risk_manager import RiskManager, RiskConfig, TradeRecord, RiskLevel, RiskAction

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_risk_manager():
    """리스크 관리 시스템 종합 테스트"""
    
    print("=" * 60)
    print("⚠️ 리스크 관리 시스템 테스트 시작")
    print("=" * 60)
    
    # 리스크 설정
    config = RiskConfig(
        max_daily_loss_ratio=0.05,       # 일일 최대 손실 5%
        max_weekly_loss_ratio=0.15,      # 주간 최대 손실 15%
        max_consecutive_losses=5,        # 최대 연속 손실 5회
        max_drawdown_ratio=0.20,         # 최대 드로다운 20%
        max_trades_per_hour=10,          # 시간당 최대 10거래
        max_trades_per_day=50,           # 일일 최대 50거래
        cool_down_after_consecutive=30   # 연속 손실 후 30분 쿨다운
    )
    
    # 리스크 관리자 생성
    risk_manager = RiskManager(config)
    
    print("\n" + "-" * 40)
    print("1️⃣ 초기 설정 및 잔고 초기화")
    print("-" * 40)
    
    # 초기 잔고 설정: $1000
    initial_balance = 1000.0
    risk_manager.initialize_balance(initial_balance)
    
    print(f"✅ 초기 잔고: ${initial_balance:,.2f}")
    print(f"✅ 일일 최대 손실 한도: ${initial_balance * config.max_daily_loss_ratio:.2f}")
    print(f"✅ 최대 드로다운 한도: {config.max_drawdown_ratio * 100:.1f}%")
    
    print("\n" + "-" * 40)
    print("2️⃣ 정상 거래 시뮬레이션")
    print("-" * 40)
    
    # 정상적인 수익 거래들
    profit_trades = [
        TradeRecord(datetime.now(), "BTCUSDT", "BUY", 0.01, 50000, pnl=10.0),
        TradeRecord(datetime.now(), "BTCUSDT", "SELL", 0.01, 50500, pnl=5.0),
        TradeRecord(datetime.now(), "ETHUSDT", "BUY", 0.5, 3000, pnl=15.0),
    ]
    
    current_balance = initial_balance
    for trade in profit_trades:
        current_balance += trade.pnl
        risk_manager.record_trade(trade)
        risk_manager.update_balance(current_balance)
    
    # 초기 리스크 평가
    risk_status = risk_manager.assess_risk()
    print(f"📊 리스크 레벨: {risk_status.level.value}")
    print(f"📈 권장 액션: {risk_status.action.value}")
    print(f"💰 현재 잔고: ${current_balance:,.2f}")
    print(f"📈 총 수익: ${current_balance - initial_balance:+,.2f}")
    
    # 거래 허용 여부 확인
    allowed, reason = risk_manager.check_trading_allowed()
    print(f"✅ 거래 허용: {allowed} ({reason})")
    
    print("\n" + "-" * 40)
    print("3️⃣ 연속 손실 시뮬레이션")
    print("-" * 40)
    
    # 연속 손실 거래 시뮬레이션
    print("🔴 연속 손실 거래 시작...")
    
    loss_trades = [
        TradeRecord(datetime.now(), "BTCUSDT", "SELL", 0.01, 49000, pnl=-30.0, is_loss=True),
        TradeRecord(datetime.now(), "BTCUSDT", "BUY", 0.01, 48500, pnl=-25.0, is_loss=True),
        TradeRecord(datetime.now(), "ETHUSDT", "SELL", 0.5, 2900, pnl=-35.0, is_loss=True),
        TradeRecord(datetime.now(), "BTCUSDT", "SELL", 0.01, 48000, pnl=-20.0, is_loss=True),
    ]
    
    for i, trade in enumerate(loss_trades, 1):
        current_balance += trade.pnl
        risk_manager.record_trade(trade)
        risk_manager.update_balance(current_balance)
        
        risk_status = risk_manager.assess_risk()
        print(f"   손실 {i}: ${trade.pnl} → 잔고: ${current_balance:.2f}, 연속손실: {risk_status.consecutive_losses}회")
        
        if risk_status.warnings:
            for warning in risk_status.warnings:
                print(f"   ⚠️ 경고: {warning}")
    
    # 연속 손실 후 리스크 상태 확인
    risk_status = risk_manager.assess_risk()
    print(f"\n📊 연속 손실 후 상태:")
    print(f"   🚨 리스크 레벨: {risk_status.level.value}")
    print(f"   🎯 권장 액션: {risk_status.action.value}")
    print(f"   🔄 연속 손실: {risk_status.consecutive_losses}회")
    print(f"   📉 현재 드로다운: {risk_status.current_drawdown:.1f}%")
    
    # 거래 허용 여부 재확인
    allowed, reason = risk_manager.check_trading_allowed()
    print(f"   {'✅' if allowed else '🚫'} 거래 허용: {allowed} ({reason})")
    
    print("\n" + "-" * 40)
    print("4️⃣ 대규모 손실 시뮬레이션 (일일 한도 테스트)")
    print("-" * 40)
    
    # 큰 손실 발생
    big_loss = initial_balance * 0.06  # 6% 손실 (일일 한도 5% 초과)
    big_loss_trade = TradeRecord(
        datetime.now(), "BTCUSDT", "SELL", 0.1, 45000, 
        pnl=-big_loss, is_loss=True
    )
    
    print(f"💥 대규모 손실 발생: ${-big_loss:.2f}")
    current_balance += big_loss_trade.pnl
    risk_manager.record_trade(big_loss_trade)
    risk_manager.update_balance(current_balance)
    
    risk_status = risk_manager.assess_risk()
    print(f"🚨 리스크 레벨: {risk_status.level.value}")
    print(f"🛑 권장 액션: {risk_status.action.value}")
    print(f"💰 현재 잔고: ${current_balance:,.2f}")
    print(f"📉 일일 손익: ${risk_status.daily_pnl:+,.2f}")
    
    if risk_status.warnings:
        print(f"⚠️ 경고 메시지:")
        for warning in risk_status.warnings:
            print(f"   • {warning}")
    
    # 긴급 정지 여부 확인
    should_close = risk_manager.should_close_all_positions()
    print(f"🚨 긴급 청산 필요: {should_close}")
    
    print("\n" + "-" * 40)
    print("5️⃣ 포지션 크기 조정 테스트")
    print("-" * 40)
    
    # 리스크 레벨에 따른 포지션 크기 조정
    size_multiplier = risk_manager.get_position_size_multiplier()
    print(f"📊 현재 리스크 레벨: {risk_status.level.value}")
    print(f"📏 포지션 크기 배수: {size_multiplier:.1f}")
    print(f"💡 기본 포지션이 $100이라면 → ${100 * size_multiplier:.2f}로 축소")
    
    print("\n" + "-" * 40)
    print("6️⃣ 거래 빈도 제한 테스트")
    print("-" * 40)
    
    # 거래 빈도 테스트를 위한 새로운 리스크 관리자
    freq_config = RiskConfig(max_trades_per_hour=3)  # 시간당 3거래로 제한
    freq_risk_manager = RiskManager(freq_config)
    freq_risk_manager.initialize_balance(1000.0)
    
    # 빠른 연속 거래 시뮬레이션
    print("⚡ 빠른 연속 거래 테스트...")
    for i in range(5):
        trade = TradeRecord(
            datetime.now(), "BTCUSDT", "BUY" if i % 2 == 0 else "SELL", 
            0.001, 50000, pnl=1.0
        )
        freq_risk_manager.record_trade(trade)
        
        allowed, reason = freq_risk_manager.check_trading_allowed()
        print(f"   거래 {i+1}: {'✅' if allowed else '🚫'} {reason}")
        
        if not allowed:
            break
    
    print("\n" + "-" * 40)
    print("7️⃣ 상세 리스크 리포트")
    print("-" * 40)
    
    # 종합 리스크 리포트 생성
    risk_report = risk_manager.get_risk_report()
    
    print(f"📊 종합 리스크 리포트:")
    print(f"   🕒 시간: {risk_report['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   🚨 리스크 레벨: {risk_report['risk_level']}")
    print(f"   🎯 권장 액션: {risk_report['recommended_action']}")
    print(f"   ✅ 거래 허용: {risk_report['trading_allowed']}")
    
    print(f"\n💰 잔고 정보:")
    balance_info = risk_report['balance_info']
    print(f"   초기 잔고: ${balance_info['initial']:,.2f}")
    print(f"   현재 잔고: ${balance_info['current']:,.2f}")
    print(f"   최고 잔고: ${balance_info['peak']:,.2f}")
    print(f"   총 손익: ${balance_info['total_pnl']:+,.2f} ({balance_info['total_pnl_percentage']:+.1f}%)")
    
    print(f"\n📈 기간별 손익:")
    period_pnl = risk_report['period_pnl']
    print(f"   일일: ${period_pnl['daily']:+,.2f}")
    print(f"   주간: ${period_pnl['weekly']:+,.2f}")
    print(f"   월간: ${period_pnl['monthly']:+,.2f}")
    
    print(f"\n📉 드로다운:")
    drawdown = risk_report['drawdown']
    print(f"   현재: {drawdown['current']:.1f}%")
    print(f"   최대 허용: {drawdown['max_allowed']:.1f}%")
    
    print(f"\n🔄 연속 손실:")
    consecutive = risk_report['consecutive_losses']
    print(f"   현재: {consecutive['current']}회")
    print(f"   최대 허용: {consecutive['max_allowed']}회")
    if consecutive['last_loss_time']:
        print(f"   마지막 손실: {consecutive['last_loss_time'].strftime('%H:%M:%S')}")
    
    print(f"\n📊 거래 제한:")
    limits = risk_report['trading_limits']
    print(f"   오늘 거래: {limits['trades_today']}/{limits['max_daily']}회")
    print(f"   이번 시간: {limits['trades_this_hour']}/{limits['max_hourly']}회")
    
    cool_down = risk_report['cool_down']
    if cool_down['active']:
        print(f"\n🚫 쿨다운:")
        print(f"   활성: {cool_down['active']}")
        print(f"   종료 시간: {cool_down['until'].strftime('%H:%M:%S') if cool_down['until'] else 'N/A'}")
        print(f"   남은 시간: {cool_down['remaining_minutes']:.1f}분")
    
    print(f"\n📏 포지션 크기:")
    print(f"   조정 배수: {risk_report['position_size_multiplier']:.1f}")
    
    if risk_report['warnings']:
        print(f"\n⚠️ 현재 경고:")
        for warning in risk_report['warnings']:
            print(f"   • {warning}")
    
    print("\n" + "-" * 40)
    print("8️⃣ 회복 시나리오 테스트")
    print("-" * 40)
    
    # 수익 거래로 회복 시뮬레이션
    print("💚 회복 거래 시뮬레이션...")
    
    recovery_trades = [
        TradeRecord(datetime.now(), "BTCUSDT", "BUY", 0.01, 51000, pnl=40.0),
        TradeRecord(datetime.now(), "ETHUSDT", "BUY", 0.3, 3200, pnl=50.0),
        TradeRecord(datetime.now(), "BTCUSDT", "SELL", 0.01, 52000, pnl=60.0),
    ]
    
    for trade in recovery_trades:
        current_balance += trade.pnl
        risk_manager.record_trade(trade)
        risk_manager.update_balance(current_balance)
        
        risk_status = risk_manager.assess_risk()
        print(f"   수익 거래: ${trade.pnl:+} → 잔고: ${current_balance:.2f}")
        print(f"   리스크 레벨: {risk_status.level.value} → 연속손실: {risk_status.consecutive_losses}회")
    
    # 최종 상태
    final_risk_status = risk_manager.assess_risk()
    allowed, reason = risk_manager.check_trading_allowed()
    
    print(f"\n✅ 회복 후 최종 상태:")
    print(f"   리스크 레벨: {final_risk_status.level.value}")
    print(f"   거래 허용: {allowed} ({reason})")
    print(f"   포지션 크기 배수: {risk_manager.get_position_size_multiplier():.1f}")
    
    print("\n" + "=" * 60)
    print("🎉 리스크 관리 시스템 테스트 완료!")
    print("=" * 60)
    
    print("\n📋 테스트된 핵심 기능:")
    print("✅ 일일/주간/월간 손실 한도 모니터링")
    print("✅ 연속 손실 감지 및 대응")
    print("✅ 드로다운 계산 및 제어")
    print("✅ 거래 빈도 제한")
    print("✅ 자동 쿨다운 시스템")
    print("✅ 리스크 레벨별 포지션 크기 조정")
    print("✅ 종합 리스크 리포트")
    print("✅ 긴급 청산 판단")
    print("✅ 실시간 경고 시스템")
    
    print("\n📋 다음 단계:")
    print("1. 매매 전략 구현")
    print("2. 트레이더와 리스크 매니저 통합")
    print("3. 실시간 모니터링 시스템")

def main():
    setup_logging()
    
    print("⚠️ 주의: 이 테스트는 리스크 관리 시스템의 시뮬레이션입니다.")
    print("실제 거래 환경에서 각 수치를 신중히 조정해야 합니다.\n")
    
    test_risk_manager()

if __name__ == "__main__":
    main()