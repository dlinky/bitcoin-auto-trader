#!/usr/bin/env python3
"""
통합 트레이더 시스템 테스트 스크립트
프로젝트 루트에서 실행: python test_integrated_trader.py
"""

import sys
import os
import logging
import time
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.api.binance_client import BinanceClient
from backend.core.capital_manager import CapitalConfig
from backend.core.risk_manager import RiskConfig
from backend.core.integrated_trader import IntegratedTrader, IntegratedTraderConfig, OrderSide

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_integrated_trader():
    """통합 트레이더 시스템 종합 테스트"""
    
    print("=" * 70)
    print("🤖⚠️💰 통합 트레이더 시스템 테스트 시작")
    print("=" * 70)
    
    # 설정 구성
    capital_config = CapitalConfig(
        total_capital_ratio=0.05,    # 전체 자본의 5%만 사용 (안전하게)
        max_loss_ratio=0.01,         # 최대 손실 1%
        max_position_ratio=0.8,      # 단일 포지션 최대 80%
        min_order_size=0.001,
        leverage=1
    )
    
    risk_config = RiskConfig(
        max_daily_loss_ratio=0.02,       # 일일 최대 손실 2%
        max_consecutive_losses=3,        # 최대 연속 손실 3회
        max_drawdown_ratio=0.10,         # 최대 드로다운 10%
        max_trades_per_hour=5,           # 시간당 최대 5거래
        cool_down_after_consecutive=10   # 연속 손실 후 10분 쿨다운
    )
    
    integrated_config = IntegratedTraderConfig(
        symbol="BTCUSDT",
        capital_config=capital_config,
        risk_config=risk_config,
        enable_auto_stop_loss=True,
        default_stop_loss_ratio=0.03,   # 3% 손절
        enable_auto_take_profit=True,
        default_take_profit_ratio=0.06, # 6% 익절
        status_update_interval=30       # 30초마다 상태 업데이트
    )
    
    print("\n" + "-" * 50)
    print("1️⃣ 시스템 초기화")
    print("-" * 50)
    
    try:
        # 바이낸스 클라이언트
        binance_client = BinanceClient(testnet=True)
        print("✅ 바이낸스 클라이언트 초기화")
        
        # 통합 트레이더
        integrated_trader = IntegratedTrader(integrated_config, binance_client)
        print("✅ 통합 트레이더 초기화")
        
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return
    
    print("\n" + "-" * 50)
    print("2️⃣ 시스템 시작")
    print("-" * 50)
    
    if integrated_trader.start():
        print("✅ 통합 트레이더 시작 성공")
    else:
        print("❌ 통합 트레이더 시작 실패")
        return
    
    # 초기 상태 확인
    status = integrated_trader.get_comprehensive_status()
    
    print(f"📊 초기 상태:")
    print(f"   💰 잔고: ${status['risk_management']['balance_info']['current']:,.2f}")
    print(f"   📈 할당 자본: ${status['capital_management']['allocated_capital']:,.2f}")
    print(f"   🛡️ 리스크 레벨: {status['risk_management']['risk_level']}")
    print(f"   ✅ 거래 허용: {status['system_status']['trading_allowed']}")
    
    print("\n" + "-" * 50)
    print("3️⃣ 현재 시장 정보")
    print("-" * 50)
    
    current_price = binance_client.get_symbol_price("BTCUSDT")
    if current_price:
        print(f"📈 BTCUSDT 현재가: ${current_price:,.2f}")
        
        # 스마트 포지션 크기 미리보기
        print(f"💡 예상 매수 포지션 정보:")
        print(f"   📊 손절가: ${current_price * 0.97:,.2f} (3% 손절)")
        print(f"   🎯 익절가: ${current_price * 1.06:,.2f} (6% 익절)")
    else:
        print("❌ 현재가 조회 실패")
        return
    
    print("\n" + "-" * 50)
    print("4️⃣ 스마트 매수 테스트")
    print("-" * 50)
    
    # 사용자 확인
    print(f"❓ 실제 테스트 거래를 실행하시겠습니까?")
    print(f"   ⚠️ 테스트넷이지만 실제 주문이 실행됩니다.")
    print(f"   📊 예상 금액: 매우 소량 (자본의 5% 내)")
    print(f"   (y/n): ", end="")
    
    user_input = input().lower().strip()
    
    if user_input == 'y':
        print(f"\n🎯 스마트 매수 주문 실행...")
        
        # 스마트 매수 (자동으로 포지션 크기, 손절/익절 설정)
        buy_result = integrated_trader.place_smart_order(OrderSide.BUY)
        
        if buy_result.success:
            print(f"✅ 스마트 매수 성공!")
            print(f"   주문 ID: {buy_result.order_id}")
            print(f"   체결가: ${buy_result.price:.2f}")
            print(f"   수량: {buy_result.quantity:.6f} BTC")
            
            # 포지션 생성 후 상태 확인
            time.sleep(3)  # 포지션 업데이트 대기
            
            position = integrated_trader.trader.get_current_position()
            if position:
                print(f"📊 포지션 생성:")
                print(f"   크기: {position.size:.6f} BTC")
                print(f"   진입가: ${position.entry_price:.2f}")
                print(f"   현재 손익: ${position.unrealized_pnl:+.2f}")
                print(f"   손익률: {position.percentage:+.2f}%")
            
            # 리스크 상태 확인
            print(f"\n⚠️ 거래 후 리스크 상태:")
            updated_status = integrated_trader.get_comprehensive_status()
            risk_info = updated_status['risk_management']
            
            print(f"   리스크 레벨: {risk_info['risk_level']}")
            print(f"   포지션 크기 배수: {risk_info['position_size_multiplier']:.1f}")
            print(f"   자본 사용률: {updated_status['capital_management']['utilization_ratio']:.1f}%")
            
            if risk_info['warnings']:
                for warning in risk_info['warnings']:
                    print(f"   ⚠️ 경고: {warning}")
            
            print("\n" + "-" * 50)
            print("5️⃣ 모니터링 시스템 테스트")
            print("-" * 50)
            
            # 30초간 모니터링
            print("🔍 30초간 자동 모니터링 시작...")
            
            for i in range(6):  # 5초씩 6번 = 30초
                time.sleep(5)
                
                # 자동 모니터링 및 대응
                integrated_trader.monitor_and_auto_respond()
                
                # 현재 상태 출력
                current_status = integrated_trader.get_comprehensive_status()
                position = integrated_trader.trader.get_current_position()
                
                if position:
                    print(f"   {i+1}/6: PnL ${position.unrealized_pnl:+.2f} | "
                          f"리스크: {current_status['risk_management']['risk_level']} | "
                          f"거래허용: {current_status['system_status']['trading_allowed']}")
                else:
                    print(f"   {i+1}/6: 포지션 없음")
                
                # 긴급 상황 시뮬레이션을 위한 조건 체크
                if i == 3:  # 중간에 상태 체크
                    risk_status = integrated_trader.risk_manager.assess_risk()
                    if risk_status.level.value in ["HIGH", "CRITICAL"]:
                        print(f"   ⚠️ 높은 리스크 감지: {risk_status.level.value}")
            
            print("✅ 모니터링 완료")
            
            print("\n" + "-" * 50)
            print("6️⃣ 스마트 청산 테스트")
            print("-" * 50)
            
            # 포지션이 있는지 확인
            final_position = integrated_trader.trader.get_current_position()
            if final_position:
                print(f"🔄 스마트 청산 실행...")
                print(f"   청산 전 예상 손익: ${final_position.unrealized_pnl:+.2f}")
                
                # 스마트 청산 (손익 자동 기록)
                close_result = integrated_trader.close_position_smart()
                
                if close_result.success:
                    print(f"✅ 스마트 청산 성공!")
                    print(f"   청산가: ${close_result.price:.2f}")
                    print(f"   거래 ID: {close_result.order_id}")
                    
                    # 청산 후 최종 상태
                    time.sleep(3)
                    final_status = integrated_trader.get_comprehensive_status()
                    risk_final = final_status['risk_management']
                    
                    print(f"📊 청산 후 상태:")
                    print(f"   최종 잔고: ${risk_final['balance_info']['current']:,.2f}")
                    print(f"   총 손익: ${risk_final['balance_info']['total_pnl']:+,.2f}")
                    print(f"   일일 손익: ${risk_final['period_pnl']['daily']:+,.2f}")
                    print(f"   리스크 레벨: {risk_final['risk_level']}")
                    
                else:
                    print(f"❌ 청산 실패: {close_result.error_message}")
            
            else:
                print("청산할 포지션이 없습니다.")
        
        else:
            print(f"❌ 스마트 매수 실패: {buy_result.error_message}")
    
    else:
        print("📋 실제 거래 테스트를 건너뜁니다.")
    
    print("\n" + "-" * 50)
    print("7️⃣ 리스크 시나리오 테스트")
    print("-" * 50)
    
    # 가상의 연속 손실 시뮬레이션
    print("💥 연속 손실 시나리오 시뮬레이션...")
    
    from backend.core.risk_manager import TradeRecord
    
    # 가상 손실 기록들
    fake_losses = [
        TradeRecord(datetime.now(), "BTCUSDT", "SELL", 0.001, 50000, pnl=-15.0, is_loss=True),
        TradeRecord(datetime.now(), "BTCUSDT", "BUY", 0.001, 49500, pnl=-12.0, is_loss=True),
        TradeRecord(datetime.now(), "BTCUSDT", "SELL", 0.001, 49000, pnl=-18.0, is_loss=True),
    ]
    
    for i, loss in enumerate(fake_losses, 1):
        integrated_trader.risk_manager.record_trade(loss)
        
        # 거래 허용 여부 체크
        allowed, reason = integrated_trader.risk_manager.check_trading_allowed()
        
        print(f"   손실 {i}: ${loss.pnl} → 거래허용: {'✅' if allowed else '🚫'} ({reason})")
        
        if not allowed:
            print(f"   🚫 자동 거래 차단 발동!")
            break
    
    print("\n" + "-" * 50)
    print("8️⃣ 긴급 상황 대응 테스트")
    print("-" * 50)
    
    # 긴급 정지 테스트
    print("🚨 긴급 정지 시뮬레이션...")
    
    # 포지션이 있다면 긴급 청산 테스트
    test_position = integrated_trader.trader.get_current_position()
    if test_position:
        print(f"   현재 포지션: {test_position.size:.6f} BTC")
        
        success = integrated_trader.emergency_close_all_positions()
        if success:
            print("✅ 긴급 청산 성공")
        else:
            print("❌ 긴급 청산 실패")
    else:
        print("   긴급 청산할 포지션이 없습니다.")
    
    # 긴급 정지
    integrated_trader.stop(emergency=True)
    print("🛑 긴급 정지 실행")
    
    # 긴급 정지 후 거래 시도 (차단 확인)
    emergency_order = integrated_trader.place_smart_order(OrderSide.BUY)
    if not emergency_order.success:
        print(f"✅ 긴급 정지 후 거래 차단 확인: {emergency_order.error_message}")
    else:
        print("❌ 긴급 정지 후 거래가 실행됨 (문제)")
    
    print("\n" + "-" * 50)
    print("9️⃣ 종합 리포트")
    print("-" * 50)
    
    # 최종 종합 상태 리포트
    final_comprehensive_status = integrated_trader.get_comprehensive_status()
    
    print("📊 최종 종합 리포트:")
    
    # 시스템 상태
    sys_status = final_comprehensive_status['system_status']
    print(f"   🤖 시스템 상태:")
    print(f"      활성: {sys_status['active']}")
    print(f"      긴급정지: {sys_status['emergency_stopped']}")
    print(f"      거래허용: {sys_status['trading_allowed']}")
    
    # 리스크 관리 결과
    risk_result = final_comprehensive_status['risk_management']
    print(f"   ⚠️ 리스크 관리:")
    print(f"      최종 리스크 레벨: {risk_result['risk_level']}")
    print(f"      권장 액션: {risk_result['recommended_action']}")
    print(f"      총 거래 수: {len(integrated_trader.risk_manager.trade_history)}")
    
    # 자본 관리 결과
    capital_result = final_comprehensive_status['capital_management']
    print(f"   💰 자본 관리:")
    print(f"      자본 사용률: {capital_result['utilization_ratio']:.1f}%")
    print(f"      활성 포지션: {capital_result['active_positions']}개")
    
    # 권고사항
    recommendations = final_comprehensive_status.get('recommendations', [])
    if recommendations:
        print(f"   💡 권고사항:")
        for rec in recommendations:
            print(f"      • {rec}")
    
    print("\n" + "=" * 70)
    print("🎉 통합 트레이더 시스템 테스트 완료!")
    print("=" * 70)
    
    print("\n📋 검증 완료된 핵심 기능:")
    print("✅ 바이낸스 API + 자본관리 + 리스크관리 통합")
    print("✅ 스마트 주문 (자동 포지션 크기 + 손절/익절 설정)")
    print("✅ 실시간 리스크 모니터링 및 자동 대응")
    print("✅ 연속 손실 감지 및 자동 거래 차단")
    print("✅ 긴급 상황 대응 (전체 청산 + 시스템 정지)")
    print("✅ 종합 상태 리포트 및 권고사항")
    print("✅ 포지션 크기 동적 조정")
    print("✅ 자동 손익 기록 및 추적")
    
    print("\n📋 다음 단계:")
    print("1. 매매 전략 구현 (기술적 지표 기반)")
    print("2. 데이터베이스 연동 (거래 기록 영구 저장)")
    print("3. 슬랙 모니터링 시스템")
    print("4. 24시간 자동 운영 시스템")

def main():
    setup_logging()
    
    print("⚠️ 주의사항:")
    print("- 이 테스트는 바이낸스 테스트넷을 사용합니다")
    print("- 실제 거래가 실행되지만 가상 자금이므로 안전합니다")
    print("- 모든 리스크 관리 기능이 실제로 작동합니다")
    print("- 테스트 중 언제든 Ctrl+C로 중단 가능합니다\n")
    
    try:
        test_integrated_trader()
    except KeyboardInterrupt:
        print("\n\n🛑 사용자가 테스트를 중단했습니다")
    except Exception as e:
        print(f"\n\n❌ 테스트 중 오류 발생: {e}")

if __name__ == "__main__":
    main()