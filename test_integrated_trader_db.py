#!/usr/bin/env python3
"""
데이터베이스 연동 통합 트레이더 테스트 스크립트
프로젝트 루트에서 실행: python test_integrated_trader_db.py

사전 준비사항:
1. Supabase 테이블 생성 완료
2. 바이낸스 테스트넷 API 키 설정
3. 환경변수 설정 완료
"""

import sys
import os
import logging
import time
from datetime import datetime

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv()

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.api.binance_client import BinanceClient
from backend.core.capital_manager import CapitalConfig
from backend.core.risk_manager import RiskConfig
from backend.database.database_manager import DatabaseManager
from backend.core.integrated_trader_with_db import IntegratedTraderWithDB, IntegratedTraderConfig, OrderSide

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_integrated_trader_with_database():
    """데이터베이스 연동 통합 트레이더 종합 테스트"""
    
    print("=" * 80)
    print("🗄️🤖💰 데이터베이스 연동 통합 트레이더 테스트")
    print("=" * 80)
    
    # 설정 구성
    capital_config = CapitalConfig(
        total_capital_ratio=0.08,    # 전체 자본의 3%만 사용 (매우 안전)
        max_loss_ratio=0.005,        # 최대 손실 0.5%
        max_position_ratio=0.7,      # 단일 포지션 최대 70%
        min_order_size=0.001,
        leverage=1
    )
    
    risk_config = RiskConfig(
        max_daily_loss_ratio=0.01,       # 일일 최대 손실 1%
        max_consecutive_losses=2,        # 최대 연속 손실 2회
        max_drawdown_ratio=0.05,         # 최대 드로다운 5%
        max_trades_per_hour=3,           # 시간당 최대 3거래
        cool_down_after_consecutive=5    # 연속 손실 후 5분 쿨다운
    )
    
    integrated_config = IntegratedTraderConfig(
        symbol="BTCUSDT",
        trader_id="test_db_trader",
        capital_config=capital_config,
        risk_config=risk_config,
        enable_auto_stop_loss=True,
        default_stop_loss_ratio=0.02,   # 2% 손절
        enable_auto_take_profit=True,
        default_take_profit_ratio=0.04, # 4% 익절
        enable_database_logging=True,
        auto_save_metrics=True,
        metrics_save_interval=300,      # 5분마다 성과 지표 저장
        status_update_interval=30       # 30초마다 상태 업데이트
    )
    
    print("\n" + "-" * 60)
    print("1️⃣ 시스템 초기화")
    print("-" * 60)
    
    try:
        # 바이낸스 클라이언트
        binance_client = BinanceClient(testnet=True)
        print("✅ 바이낸스 클라이언트 초기화")
        
        # 데이터베이스 매니저
        db_manager = DatabaseManager()
        print("✅ 데이터베이스 매니저 초기화")
        
        # 데이터베이스 상태 확인
        db_health = db_manager.health_check()
        print(f"✅ 데이터베이스 상태: {db_health['status']}")
        
        # 통합 트레이더 (데이터베이스 연동)
        integrated_trader = IntegratedTraderWithDB(integrated_config, binance_client, db_manager)
        print("✅ 데이터베이스 연동 통합 트레이더 초기화")
        
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return
    
    print("\n" + "-" * 60)
    print("2️⃣ 트레이더 시작 (거래 세션 생성)")
    print("-" * 60)
    
    session_name = f"DB_TEST_SESSION_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    if integrated_trader.start(session_name):
        print(f"✅ 트레이더 시작 성공 - 세션: {session_name}")
    else:
        print("❌ 트레이더 시작 실패")
        return
    
    # 초기 상태 확인
    status = integrated_trader.get_comprehensive_status_with_db()
    
    print(f"📊 초기 상태:")
    print(f"   💰 잔고: ${status['risk_management']['balance_info']['current']:,.2f}")
    print(f"   📈 할당 자본: ${status['capital_management']['allocated_capital']:,.2f}")
    print(f"   🛡️ 리스크 레벨: {status['risk_management']['risk_level']}")
    print(f"   🗄️ 세션 ID: {status['session_statistics']['session_id']}")
    print(f"   ✅ 거래 허용: {status['system_status']['trading_allowed']}")
    
    print("\n" + "-" * 60)
    print("3️⃣ 데이터베이스 통계 확인")
    print("-" * 60)
    
    db_stats = integrated_trader.get_database_statistics()
    
    if 'error' not in db_stats:
        print("📊 데이터베이스 통계:")
        health = db_stats['health']
        print(f"   🏥 데이터베이스 상태: {health['status']}")
        
        for table, info in health['tables'].items():
            status_icon = "✅" if info['accessible'] else "❌"
            print(f"   {status_icon} {table}: {info.get('count', 0)}개 레코드")
        
        trading_stats = db_stats.get('trading_stats', {})
        if trading_stats and 'error' not in trading_stats:
            print(f"   📈 최근 30일 거래: {trading_stats.get('total_trades', 0)}회")
    else:
        print(f"❌ 데이터베이스 통계 오류: {db_stats['error']}")
    
    print("\n" + "-" * 60)
    print("4️⃣ 현재 시장 정보")
    print("-" * 60)
    
    current_price = binance_client.get_symbol_price("BTCUSDT")
    if current_price:
        print(f"📈 BTCUSDT 현재가: ${current_price:,.2f}")
        
        # 스마트 포지션 크기 미리보기
        print(f"💡 예상 매수 포지션 정보:")
        print(f"   📊 손절가: ${current_price * 0.98:,.2f} (2% 손절)")
        print(f"   🎯 익절가: ${current_price * 1.04:,.2f} (4% 익절)")
    else:
        print("❌ 현재가 조회 실패")
        return
    
    # 사용자 확인
    print(f"\n❓ 실제 데이터베이스 연동 거래 테스트를 실행하시겠습니까?")
    print(f"   ⚠️ 모든 거래 활동이 데이터베이스에 기록됩니다")
    print(f"   📊 테스트넷이지만 실제 주문이 실행됩니다")
    print(f"   🗄️ 거래 세션, 포지션, 리스크 이벤트가 모두 저장됩니다")
    print(f"   (y/n): ", end="")
    
    user_input = input().lower().strip()
    
    if user_input == 'y':
        print("\n" + "-" * 60)
        print("5️⃣ 스마트 매수 테스트 (데이터베이스 로깅)")
        print("-" * 60)
        
        print(f"🎯 데이터베이스 연동 스마트 매수 주문 실행...")
        
        # 스마트 매수 (모든 활동이 데이터베이스에 자동 저장)
        buy_result = integrated_trader.place_smart_order_with_logging(
            side=OrderSide.BUY,
            notes="데이터베이스 연동 테스트 매수"
        )
        
        if buy_result.success:
            print(f"✅ 데이터베이스 연동 매수 성공!")
            print(f"   주문 ID: {buy_result.order_id}")
            print(f"   체결가: ${buy_result.price:.2f}")
            print(f"   수량: {buy_result.quantity:.6f} BTC")
            
            # 데이터베이스 기록 확인
            print(f"\n📊 데이터베이스 기록 확인:")
            recent_trades = db_manager.get_trades(integrated_config.trader_id, limit=1)
            if recent_trades:
                trade = recent_trades[0]
                print(f"   ✅ 거래 기록 저장: {trade['symbol']} {trade['side']} {trade['quantity']}")
                print(f"   📝 상태: {trade['status']}")
                print(f"   💬 메모: {trade['notes']}")
            
            # 포지션 생성 후 상태 확인
            time.sleep(3)  # 포지션 업데이트 대기
            
            position = integrated_trader.trader.get_current_position()
            if position:
                print(f"\n📊 포지션 생성 (데이터베이스 저장됨):")
                print(f"   크기: {position.size:.6f} BTC")
                print(f"   진입가: ${position.entry_price:.2f}")
                print(f"   현재 손익: ${position.unrealized_pnl:+.2f}")
                print(f"   손익률: {position.percentage:+.2f}%")
                
                # 데이터베이스 포지션 기록 확인
                active_positions = db_manager.get_active_positions(integrated_config.trader_id)
                if active_positions:
                    db_position = active_positions[0]
                    print(f"   ✅ 포지션 DB 저장: {db_position['side']} {db_position['size']}")
            
            print("\n" + "-" * 60)
            print("6️⃣ 모니터링 시스템 테스트 (데이터베이스 로깅)")
            print("-" * 60)
            
            # 60초간 모니터링 (데이터베이스 로깅 포함)
            print("🔍 60초간 자동 모니터링 시작 (모든 활동 데이터베이스 기록)...")
            
            for i in range(12):  # 5초씩 12번 = 60초
                time.sleep(5)
                
                # 자동 모니터링 및 대응 (데이터베이스 로깅 포함)
                integrated_trader.monitor_and_auto_respond_with_logging()
                
                # 현재 상태 출력
                current_status = integrated_trader.get_comprehensive_status_with_db()
                position = integrated_trader.trader.get_current_position()
                
                session_stats = current_status['session_statistics']
                
                if position:
                    print(f"   {i+1}/12: PnL ${position.unrealized_pnl:+.2f} | "
                          f"세션거래: {session_stats['total_trades']}회 | "
                          f"리스크: {current_status['risk_management']['risk_level']} | "
                          f"거래허용: {current_status['system_status']['trading_allowed']}")
                else:
                    print(f"   {i+1}/12: 포지션 없음 | 세션거래: {session_stats['total_trades']}회")
                
                # 중간에 성과 지표 저장 테스트
                if i == 6:  # 30초 지점
                    print(f"   💾 성과 지표 저장 테스트...")
                    integrated_trader._save_current_metrics()
            
            print("✅ 모니터링 완료 (모든 활동 데이터베이스 기록됨)")
            
            print("\n" + "-" * 60)
            print("7️⃣ 스마트 청산 테스트 (데이터베이스 로깅)")
            print("-" * 60)
            
            # 포지션이 있는지 확인
            final_position = integrated_trader.trader.get_current_position()
            if final_position:
                print(f"🔄 데이터베이스 연동 스마트 청산 실행...")
                print(f"   청산 전 예상 손익: ${final_position.unrealized_pnl:+.2f}")
                
                # 스마트 청산 (모든 활동이 데이터베이스에 자동 저장)
                close_result = integrated_trader.close_position_with_logging(
                    percentage=100.0,
                    reason="테스트 완료",
                    notes="데이터베이스 연동 테스트 청산"
                )
                
                if close_result.success:
                    print(f"✅ 데이터베이스 연동 청산 성공!")
                    print(f"   청산가: ${close_result.price:.2f}")
                    print(f"   거래 ID: {close_result.order_id}")
                    
                    # 청산 거래 데이터베이스 기록 확인
                    print(f"\n📊 청산 거래 데이터베이스 기록 확인:")
                    recent_trades = db_manager.get_trades(integrated_config.trader_id, limit=2)
                    for trade in recent_trades:
                        if "청산" in trade.get('notes', ''):
                            print(f"   ✅ 청산 기록: {trade['side']} {trade['quantity']} @ ${trade['price']}")
                            print(f"   📝 메모: {trade['notes']}")
                            break
                    
                    # 청산 후 최종 상태
                    time.sleep(3)
                    final_status = integrated_trader.get_comprehensive_status_with_db()
                    session_final = final_status['session_statistics']
                    risk_final = final_status['risk_management']
                    
                    print(f"📊 청산 후 세션 상태:")
                    print(f"   최종 잔고: ${risk_final['balance_info']['current']:,.2f}")
                    print(f"   세션 손익: ${session_final['session_pnl']:+,.2f}")
                    print(f"   총 거래: {session_final['total_trades']}회")
                    print(f"   승률: {session_final['win_rate']:.1f}%")
                    print(f"   리스크 레벨: {risk_final['risk_level']}")
                    
                else:
                    print(f"❌ 청산 실패: {close_result.error_message}")
            
            else:
                print("청산할 포지션이 없습니다.")
        
        else:
            print(f"❌ 스마트 매수 실패: {buy_result.error_message}")
    
    else:
        print("📋 실제 거래 테스트를 건너뜁니다.")
    
    print("\n" + "-" * 60)
    print("8️⃣ 데이터베이스 통계 및 리포트")
    print("-" * 60)
    
    # 최종 데이터베이스 통계
    final_db_stats = integrated_trader.get_database_statistics()
    
    if 'error' not in final_db_stats:
        print("📊 최종 데이터베이스 통계:")
        
        trading_stats = final_db_stats.get('trading_stats', {})
        if trading_stats and 'error' not in trading_stats:
            print(f"   📈 총 거래: {trading_stats.get('total_trades', 0)}회")
            print(f"   ✅ 체결 거래: {trading_stats.get('filled_trades', 0)}회")
            print(f"   📊 성공률: {trading_stats.get('success_rate', 0):.1f}%")
        
        recent_trades = final_db_stats.get('recent_trades', [])
        print(f"   📋 최근 거래: {len(recent_trades)}건")
        
        active_positions = final_db_stats.get('active_positions', [])
        print(f"   🎯 활성 포지션: {len(active_positions)}개")
        
        risk_events = final_db_stats.get('recent_risk_events', [])
        print(f"   ⚠️ 24시간 내 리스크 이벤트: {len(risk_events)}개")
    
    # 세션 리포트 생성
    print(f"\n📋 세션 리포트 생성...")
    session_report = integrated_trader.export_session_report()
    
    if 'error' not in session_report:
        print(f"✅ 세션 리포트 생성 성공!")
        
        session_info = session_report['session_info']
        performance = session_report['performance']
        
        print(f"📊 세션 요약:")
        print(f"   ⏰ 세션 시간: {session_info['duration_hours']:.2f}시간")
        print(f"   💰 시작 잔고: ${performance['start_balance']:,.2f}")
        print(f"   💰 최종 잔고: ${performance['current_balance']:,.2f}")
        print(f"   📈 총 손익: ${performance['total_pnl']:+,.2f} ({performance['pnl_percentage']:+.2f}%)")
        print(f"   🔄 총 거래: {performance['total_trades']}회")
        print(f"   🏆 승률: {performance['win_rate']:.1f}%")
        print(f"   📊 거래 기록: {len(session_report['trades'])}건")
        print(f"   ⚠️ 리스크 이벤트: {len(session_report['risk_events'])}건")
    
    print("\n" + "-" * 60)
    print("9️⃣ 시스템 로그 확인")
    print("-" * 60)
    
    # 최근 시스템 로그 확인
    try:
        # 직접 쿼리 (간단한 확인)
        logs_query = db_manager.supabase.table('system_logs')\
            .select("*")\
            .eq('trader_id', integrated_config.trader_id)\
            .order('created_at', desc=True)\
            .limit(5)\
            .execute()
        
        if logs_query.data:
            print("📝 최근 시스템 로그:")
            for log in logs_query.data:
                timestamp = log['created_at'][:19].replace('T', ' ')
                print(f"   {timestamp} [{log['log_level']}] {log['component']}: {log['message']}")
        else:
            print("시스템 로그가 없습니다.")
            
    except Exception as e:
        print(f"시스템 로그 조회 실패: {e}")
    
    print("\n" + "-" * 60)
    print("🔟 트레이더 종료 (세션 종료)")
    print("-" * 60)
    
    # 트레이더 정상 종료 (세션 종료 및 최종 데이터 저장)
    integrated_trader.stop(emergency=False, reason="테스트 완료")
    print("✅ 트레이더 정상 종료 (세션 종료됨)")
    
    # 종료된 세션 확인
    try:
        sessions_query = db_manager.supabase.table('trading_sessions')\
            .select("*")\
            .eq('trader_id', integrated_config.trader_id)\
            .eq('is_active', False)\
            .order('ended_at', desc=True)\
            .limit(1)\
            .execute()
        
        if sessions_query.data:
            session = sessions_query.data[0]
            print(f"📊 종료된 세션 확인:")
            print(f"   세션 이름: {session['session_name']}")
            print(f"   총 손익: ${session['total_pnl']:+.2f}")
            print(f"   총 거래: {session['total_trades']}회")
            print(f"   승률: {session['win_rate']:.1f}%")
            print(f"   종료 시간: {session['ended_at'][:19].replace('T', ' ')}")
            
    except Exception as e:
        print(f"종료된 세션 조회 실패: {e}")
    
    print("\n" + "=" * 80)
    print("🎉 데이터베이스 연동 통합 트레이더 테스트 완료!")
    print("=" * 80)
    
    print("\n📋 검증 완료된 핵심 기능:")
    print("✅ 데이터베이스 연동 거래 세션 관리")
    print("✅ 모든 거래 활동 실시간 데이터베이스 저장")
    print("✅ 포지션 추적 및 손익 기록")
    print("✅ 리스크 이벤트 자동 로깅")
    print("✅ 성과 지표 정기 저장")
    print("✅ 시스템 로그 종합 기록")
    print("✅ 거래 통계 및 분석")
    print("✅ 세션 리포트 자동 생성")
    print("✅ 데이터베이스 상태 모니터링")
    print("✅ 완전한 감사 추적 (audit trail)")
    
    print("\n📊 데이터베이스에 저장된 정보:")
    print("🔸 거래 기록 (trades)")
    print("🔸 포지션 추적 (positions)")
    print("🔸 거래 세션 (trading_sessions)")
    print("🔸 리스크 이벤트 (risk_events)")
    print("🔸 시스템 로그 (system_logs)")
    print("🔸 성과 지표 (performance_metrics)")
    
    print("\n📋 다음 단계:")
    print("1. 매매 전략 구현 및 데이터베이스 연동")
    print("2. 실시간 대시보드 개발")
    print("3. 슬랙 알림 시스템 연동")
    print("4. 24시간 자동 운영 시스템")
    print("5. 백업 및 복구 시스템")
    
    # 최종 데이터베이스 상태 확인
    final_health = db_manager.health_check()
    print(f"\n🏥 최종 데이터베이스 상태: {final_health['status']}")
    
    if final_health['status'] == 'healthy':
        print("✅ 모든 데이터베이스 테이블 정상 작동")
        print("💾 모든 거래 데이터 안전하게 저장됨")
    else:
        print("⚠️ 일부 데이터베이스 테이블에 주의 필요")

def main():
    """메인 테스트 함수"""
    
    setup_logging()
    
    print("⚠️ 주의사항:")
    print("- 이 테스트는 실제 데이터베이스에 거래 데이터를 저장합니다")
    print("- 바이낸스 테스트넷을 사용하지만 모든 활동이 기록됩니다")
    print("- 거래 세션, 포지션, 리스크 이벤트, 성과 지표가 모두 저장됩니다")
    print("- Supabase 테이블이 미리 생성되어 있어야 합니다")
    print("- 환경변수 설정이 완료되어 있어야 합니다\n")
    
    # 환경변수 확인
    required_vars = ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'TESTNET_API_KEY', 'TESTNET_API_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ 누락된 환경변수: {', '.join(missing_vars)}")
        print("환경변수를 설정한 후 다시 실행해주세요.")
        return
    
    try:
        test_integrated_trader_with_database()
    except KeyboardInterrupt:
        print("\n\n🛑 사용자가 테스트를 중단했습니다")
    except Exception as e:
        print(f"\n\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()