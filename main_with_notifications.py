#!/usr/bin/env python3
"""
암호화폐 자동매매 메인 시스템 (알림 통합 버전)
파일 위치: main_with_notifications.py
"""

import os
import sys
import signal
import time
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로 설정
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.api.binance_client import BinanceClient
from src.api.supabase_client import SupabaseClient
from src.core.data_collector import DataCollector
from src.core.trader import Trader
from src.core.notification_manager import NotificationManager
from src.core.scheduler import EnhancedScheduler
from src.strategies.macd_atr import MACDATRStrategy
from src.utils.logger import get_logger

# 로거 설정
logger = get_logger(__name__)

class IntegratedTradingSystem:
    """통합된 자동매매 시스템"""
    
    def __init__(self):
        """시스템 초기화"""
        self.binance_client = None
        self.supabase_client = None
        self.notification_manager = None
        self.data_collector = None
        self.scheduler = None
        self.traders = []
        
        # 시스템 상태
        self.is_initialized = False
        self.is_running = False
        
        logger.info("IntegratedTradingSystem 초기화")
    
    def initialize(self) -> bool:
        """시스템 구성 요소 초기화"""
        try:
            logger.info("시스템 초기화 시작...")
            
            # 1. 환경변수 로드
            env_path = project_root / 'config' / '.env'
            if env_path.exists():
                load_dotenv(env_path)
                logger.info("환경변수 로드 완료")
            else:
                logger.error(f".env 파일이 없습니다: {env_path}")
                return False
            
            # 2. Supabase 클라이언트 초기화
            logger.info("Supabase 클라이언트 초기화...")
            self.supabase_client = SupabaseClient()
            
            # 3. Binance 클라이언트 초기화  
            logger.info("Binance 클라이언트 초기화...")
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_API_SECRET')
            
            if not api_key or not api_secret:
                logger.error("Binance API 키가 설정되지 않았습니다")
                return False
            
            self.binance_client = BinanceClient(api_key, api_secret)
            
            # 4. NotificationManager 초기화 (Slack 연동)
            logger.info("NotificationManager 초기화...")
            self.notification_manager = NotificationManager(self.supabase_client)
            
            # 5. DataCollector 초기화
            logger.info("DataCollector 초기화...")
            symbols = ['BTCUSDT']  # 초기 심볼
            self.data_collector = DataCollector(
                self.binance_client, 
                self.supabase_client, 
                symbols
            )
            
            # 6. 트레이더 초기화
            logger.info("트레이더 초기화...")
            if not self._initialize_traders():
                return False
            
            # 7. 스케줄러 초기화 (NotificationManager 포함)
            logger.info("스케줄러 초기화...")
            self.scheduler = EnhancedScheduler(self.notification_manager)
            
            self.is_initialized = True
            logger.info("시스템 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"시스템 초기화 실패: {e}")
            return False
    
    def _initialize_traders(self) -> bool:
        """트레이더 초기화"""
        try:
            # DB에서 활성 트레이더 정보 조회
            active_traders = self.supabase_client.get_active_traders()
            
            if not active_traders:
                logger.warning("활성 트레이더가 없습니다")
                return True  # 트레이더가 없어도 시스템은 시작 가능
            
            for trader_info in active_traders:
                # 전략 생성 (현재는 MACD+ATR만 지원)
                strategy = MACDATRStrategy()
                
                # 트레이더 생성
                trader = Trader(
                    trader_id=trader_info['id'],
                    symbol=trader_info['symbol'],
                    binance_client=self.binance_client,
                    supabase_client=self.supabase_client,
                    strategy=strategy,
                    allocated_budget=float(trader_info['allocated_budget']),
                    investment_ratio=float(trader_info['investment_amount']) / float(trader_info['allocated_budget'])
                )
                
                self.traders.append(trader)
                logger.info(f"트레이더 생성: {trader_info['name']} ({trader_info['symbol']})")
            
            logger.info(f"총 {len(self.traders)}개 트레이더 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"트레이더 초기화 실패: {e}")
            return False
    
    def start(self) -> bool:
        """시스템 시작"""
        try:
            if not self.is_initialized:
                logger.error("시스템이 초기화되지 않았습니다")
                return False
            
            if self.is_running:
                logger.warning("시스템이 이미 실행 중입니다")
                return True
            
            logger.info("자동매매 시스템 시작...")
            
            # 1. 스케줄러 시작 (NotificationManager도 함께 시작됨)
            if not self.scheduler.start():
                logger.error("스케줄러 시작 실패")
                return False
            
            # 2. 과거 데이터 보완
            logger.info("과거 데이터 보완 중...")
            for symbol in self.data_collector.symbols:
                success = self.data_collector.ensure_historical_data(symbol, 200)
                if not success:
                    logger.warning(f"{symbol} 과거 데이터 보완 실패")
            
            # 3. 스케줄 작업 등록
            
            # 데이터 수집 작업 (매분)
            self.scheduler.add_data_collection_job(
                self.data_collector, 
                self.data_collector.symbols
            )
            
            # 트레이딩 작업 (매분)
            if self.traders:
                self.scheduler.add_trading_job(self.traders)
            
            # 시스템 상태 리포트 (1시간마다)
            self.scheduler.add_system_status_job(interval_minutes=60)
            
            self.is_running = True
            
            # 시작 완료 알림
            if self.notification_manager:
                self.notification_manager.send_system_status({
                    'system_status': 'running',
                    'uptime': '방금 시작됨',
                    'active_traders': len(self.traders),
                    'last_trade': 'N/A',
                    'errors_today': 0
                })
                
                # 시작 알림
                self.notification_manager.send_error_alert(
                    "🚀 자동매매 시스템이 시작되었습니다!",
                    "integrated_trading_system",
                    "INFO",
                    {
                        "active_traders": len(self.traders),
                        "symbols": self.data_collector.symbols,
                        "start_time": time.strftime('%Y-%m-%d %H:%M:%S')
                    },
                    throttle=False  # 시작 알림은 스팸 방지 무시
                )
            
            logger.info(f"자동매매 시스템 시작 완료! (트레이더: {len(self.traders)}개)")
            return True
            
        except Exception as e:
            logger.error(f"시스템 시작 실패: {e}")
            return False
    
    def stop(self):
        """시스템 정지"""
        try:
            if not self.is_running:
                logger.info("시스템이 이미 정지된 상태입니다")
                return
            
            logger.info("자동매매 시스템 정지 중...")
            
            # 정지 알림
            if self.notification_manager:
                self.notification_manager.send_error_alert(
                    "⏹️ 자동매매 시스템이 정지됩니다.",
                    "integrated_trading_system", 
                    "INFO",
                    {
                        "stop_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "active_traders": len(self.traders)
                    },
                    throttle=False
                )
            
            # 스케줄러 정지 (NotificationManager도 함께 정지됨)
            if self.scheduler:
                self.scheduler.stop()
            
            self.is_running = False
            logger.info("자동매매 시스템 정지 완료")
            
        except Exception as e:
            logger.error(f"시스템 정지 중 에러: {e}")
    
    def get_system_status(self) -> dict:
        """시스템 상태 조회"""
        status = {
            'initialized': self.is_initialized,
            'running': self.is_running,
            'traders_count': len(self.traders),
            'symbols': self.data_collector.symbols if self.data_collector else [],
        }
        
        if self.scheduler:
            status['scheduler'] = self.scheduler.get_job_status()
        
        if self.notification_manager:
            status['notifications'] = self.notification_manager.get_notification_status()
        
        return status
    
    def send_test_notifications(self) -> bool:
        """테스트 알림 전송"""
        if not self.notification_manager:
            logger.error("NotificationManager가 없습니다")
            return False
        
        return self.scheduler.send_test_notification()


def signal_handler(signum, frame):
    """시그널 핸들러 (Ctrl+C 처리)"""
    logger.info(f"시그널 수신: {signum}")
    if 'trading_system' in globals():
        trading_system.stop()
    sys.exit(0)


def main():
    """메인 함수"""
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 종료 신호
    
    try:
        # 시스템 생성 및 초기화
        global trading_system
        trading_system = IntegratedTradingSystem()
        
        if not trading_system.initialize():
            logger.error("시스템 초기화 실패")
            sys.exit(1)
        
        # 시스템 시작
        if not trading_system.start():
            logger.error("시스템 시작 실패")
            sys.exit(1)
        
        # 테스트 알림 전송
        logger.info("테스트 알림 전송...")
        trading_system.send_test_notifications()
        
        # 메인 루프
        logger.info("메인 루프 시작 - 시스템이 백그라운드에서 실행됩니다")
        logger.info("정지하려면 Ctrl+C를 누르세요")
        
        # 상태 출력 (10분마다)
        last_status_time = time.time()
        status_interval = 600  # 10분
        
        while trading_system.is_running:
            try:
                time.sleep(30)  # 30초마다 체크
                
                # 주기적 상태 출력
                current_time = time.time()
                if current_time - last_status_time >= status_interval:
                    status = trading_system.get_system_status()
                    logger.info(f"시스템 상태: 실행 중 (트레이더: {status['traders_count']}개)")
                    last_status_time = current_time
                
            except KeyboardInterrupt:
                logger.info("키보드 인터럽트 - 시스템 정지")
                break
            except Exception as e:
                logger.error(f"메인 루프 에러: {e}")
                time.sleep(10)  # 10초 대기 후 재시도
        
    except Exception as e:
        logger.error(f"메인 함수 에러: {e}")
        sys.exit(1)
    
    finally:
        # 정리
        if 'trading_system' in locals():
            trading_system.stop()


if __name__ == "__main__":
    """
    통합된 자동매매 시스템 실행
    
    필요한 환경변수 (config/.env):
    - BINANCE_API_KEY=your_api_key
    - BINANCE_API_SECRET=your_secret_key
    - SUPABASE_URL=your_supabase_url
    - SUPABASE_KEY=your_supabase_key
    - SLACK_BOT_TOKEN=xoxb-your-token
    - SLACK_CHANNEL_ID=C1234567890
    """
    
    print("=" * 60)
    print("🚀 암호화폐 자동매매 시스템 (알림 통합 버전)")
    print("=" * 60)
    print()
    
    # 환경변수 체크
    required_env_vars = [
        'BINANCE_API_KEY', 'BINANCE_API_SECRET',
        'SUPABASE_URL', 'SUPABASE_KEY',
        'SLACK_BOT_TOKEN', 'SLACK_CHANNEL_ID'
    ]
    
    env_path = project_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ .env 파일 로드 완료")
    else:
        print("❌ .env 파일을 찾을 수 없습니다")
        print(f"   파일 위치: {env_path}")
        sys.exit(1)
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ 누락된 환경변수:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n.env 파일을 확인해주세요")
        sys.exit(1)
    
    print("✅ 모든 환경변수 설정 완료")
    print()
    
    # 메인 함수 실행
    main()