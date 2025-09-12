#!/usr/bin/env python3
"""
매매 시스템 스케줄러
파일 위치: src/core/scheduler.py
"""

import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import schedule

from src.utils.logger import get_logger

logger = get_logger(__name__)

class TradingScheduler:
    """매매 시스템 스케줄러 - 매분 0초에 데이터 수집 및 매매 실행"""
    
    def __init__(self, data_collector, traders: List, slack_bot=None):
        """
        스케줄러 초기화
        
        Args:
            data_collector: DataCollector 인스턴스
            traders: Trader 인스턴스들의 리스트
            slack_bot: SlackBot 인스턴스 (옵션)
        """
        self.data_collector = data_collector
        self.traders = traders
        self.slack_bot = slack_bot
        
        self.is_running = False
        self.scheduler_thread = None
        self.last_execution_time = None
        
        # 통계 정보
        self.total_cycles = 0
        self.successful_cycles = 0
        self.failed_cycles = 0
        
        logger.info(f"TradingScheduler 초기화 완료 - 트레이더 {len(traders)}개")
    
    def start(self):
        """스케줄러 시작"""
        if self.is_running:
            logger.warning("스케줄러가 이미 실행 중입니다")
            return
        
        self.is_running = True
        
        # 매분 0초에 실행하도록 스케줄 설정
        schedule.every().minute.at(":00").do(self._execute_trading_cycle)
        
        # 스케줄러를 별도 스레드에서 실행
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("TradingScheduler 시작됨")
        
        if self.slack_bot:
            self.slack_bot.send_message("🚀 자동매매 시스템 시작")
    
    def stop(self):
        """스케줄러 정지"""
        self.is_running = False
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        logger.info("TradingScheduler 정지됨")
        
        if self.slack_bot:
            self.slack_bot.send_message("⏹️ 자동매매 시스템 정지")
    
    def _run_scheduler(self):
        """스케줄러 메인 루프"""
        logger.info("스케줄러 스레드 시작")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)  # 1초마다 스케줄 확인
                
            except Exception as e:
                logger.error(f"스케줄러 루프 에러: {e}")
                time.sleep(5)  # 에러 시 5초 대기
        
        logger.info("스케줄러 스레드 종료")
    
    def _execute_trading_cycle(self):
        """매분 실행되는 메인 트레이딩 사이클"""
        if not self.is_running:
            return
        
        start_time = time.time()
        current_time = datetime.now()
        
        logger.info(f"=== 트레이딩 사이클 시작: {current_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        try:
            self.total_cycles += 1
            
            # 1단계: 데이터 수집 (모든 심볼 동시)
            data_collection_start = time.time()
            try:
                collection_results = self.data_collector.collect_all_symbols_concurrent()
                data_collection_time = time.time() - data_collection_start
                
                logger.info(f"데이터 수집 완료 ({data_collection_time:.1f}초): {sum(collection_results.values())}/{len(collection_results)}개 성공")
            except Exception as e:
                logger.error(f"데이터 수집 실패: {e}")
                collection_results = {}
                data_collection_time = 0
            
            # 2단계: 트레이더 실행 (순차)
            trading_start = time.time()
            trading_results = []
            
            for trader in self.traders:
                if not trader.is_active:
                    continue
                
                try:
                    result = trader.execute_trading_cycle()
                    trading_results.append(result)
                    
                    # 거래 발생시 슬랙 알림
                    if self.slack_bot and result.get('success') and result.get('signal_result'):
                        signal_result = result['signal_result']
                        if signal_result.get('action') in ['entry', 'exit']:
                            self._send_trading_notification(trader, signal_result)
                    
                except Exception as e:
                    logger.error(f"Trader {trader.trader_id if hasattr(trader, 'trader_id') else 'Unknown'} 실행 실패: {e}")
                    trading_results.append({
                        'success': False,
                        'trader_id': getattr(trader, 'trader_id', 'Unknown'),
                        'symbol': getattr(trader, 'symbol', 'Unknown'),
                        'reason': str(e)
                    })
            
            trading_time = time.time() - trading_start
            
            # 3단계: 결과 집계
            successful_traders = sum(1 for r in trading_results if r.get('success', False))
            total_traders = len(trading_results)
            
            total_time = time.time() - start_time
            self.last_execution_time = current_time
            
            # 성공/실패 통계 업데이트
            collection_success = len(collection_results) == 0 or sum(collection_results.values()) == len(collection_results)
            trading_success = successful_traders == total_traders if total_traders > 0 else True
            
            if collection_success and trading_success:
                self.successful_cycles += 1
            else:
                self.failed_cycles += 1
            
            # 결과 로깅
            logger.info(f"트레이딩 실행 완료 ({trading_time:.1f}초): {successful_traders}/{total_traders}개 트레이더 성공")
            logger.info(f"=== 트레이딩 사이클 완료: 총 {total_time:.1f}초 ===")
            
            # 주기적 상태 리포트 (10분마다)
            if self.total_cycles % 10 == 0:
                self._send_status_report()
            
        except Exception as e:
            self.failed_cycles += 1
            logger.error(f"트레이딩 사이클 실행 중 에러: {e}")
            
            if self.slack_bot:
                self.slack_bot.send_message(f"❌ 트레이딩 사이클 에러: {str(e)[:200]}")
    
    def _send_trading_notification(self, trader, signal_result):
        """거래 알림 전송"""
        try:
            action = signal_result.get('action')
            direction = signal_result.get('direction')
            symbol = trader.symbol
            
            if action == 'entry':
                price = signal_result.get('price', 0)
                quantity = signal_result.get('quantity', 0)
                
                emoji = "📈" if direction == 'LONG' else "📉"
                message = f"{emoji} {symbol} {direction} 포지션 진입\n"
                message += f"💰 수량: {quantity:.6f}\n"
                message += f"💵 가격: ${price:,.4f}"
                
            elif action == 'exit':
                entry_price = signal_result.get('entry_price', 0)
                exit_price = signal_result.get('exit_price', 0)
                realized_pnl = signal_result.get('realized_pnl', 0)
                quantity = signal_result.get('quantity', 0)
                
                emoji = "✅" if realized_pnl >= 0 else "❌"
                pnl_emoji = "💰" if realized_pnl >= 0 else "💸"
                
                message = f"{emoji} {symbol} {direction} 포지션 청산\n"
                message += f"💰 수량: {quantity:.6f}\n"
                message += f"📊 진입: ${entry_price:,.4f} → 청산: ${exit_price:,.4f}\n"
                message += f"{pnl_emoji} 손익: ${realized_pnl:,.2f}"
            
            else:
                return  # 다른 액션은 알림 안함
            
            self.slack_bot.send_message(message)
            
        except Exception as e:
            logger.error(f"거래 알림 전송 실패: {e}")
    
    def _send_status_report(self):
        """상태 리포트 전송 (10분마다)"""
        try:
            if not self.slack_bot:
                return
            
            # 전체 통계
            success_rate = (self.successful_cycles / max(1, self.total_cycles)) * 100
            
            message = f"📊 자동매매 상태 리포트\n"
            message += f"🔄 총 사이클: {self.total_cycles}회\n"
            message += f"✅ 성공률: {success_rate:.1f}%\n"
            message += f"⏰ 마지막 실행: {self.last_execution_time.strftime('%H:%M:%S') if self.last_execution_time else 'N/A'}\n"
            
            # 트레이더별 상태
            message += f"\n👥 트레이더 상태:\n"
            for trader in self.traders:
                status = trader.get_trader_status()
                active_status = "🟢" if status['is_active'] else "🔴"
                position_info = status['current_position'] or "대기"
                
                message += f"{active_status} {status['symbol']}: {position_info}"
                if status['unrealized_pnl'] != 0:
                    pnl_emoji = "📈" if status['unrealized_pnl'] >= 0 else "📉"
                    message += f" {pnl_emoji} ${status['unrealized_pnl']:.2f}"
                message += "\n"
            
            self.slack_bot.send_message(message)
            
        except Exception as e:
            logger.error(f"상태 리포트 전송 실패: {e}")
    
    def get_scheduler_status(self) -> Dict:
        """스케줄러 상태 정보 반환"""
        return {
            'is_running': self.is_running,
            'total_cycles': self.total_cycles,
            'successful_cycles': self.successful_cycles,
            'failed_cycles': self.failed_cycles,
            'success_rate': (self.successful_cycles / max(1, self.total_cycles)) * 100,
            'last_execution_time': self.last_execution_time.isoformat() if self.last_execution_time else None,
            'active_traders': len([t for t in self.traders if t.is_active]),
            'total_traders': len(self.traders)
        }
    
    def force_execute_cycle(self):
        """수동으로 트레이딩 사이클 실행 (테스트용)"""
        logger.info("수동 트레이딩 사이클 실행")
        self._execute_trading_cycle()
    
    def wait_for_next_minute(self):
        """다음 분까지 대기 (정확한 시작을 위해)"""
        now = datetime.now()
        next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        wait_seconds = (next_minute - now).total_seconds()
        
        if wait_seconds > 0:
            logger.info(f"다음 실행까지 {wait_seconds:.1f}초 대기")
            time.sleep(wait_seconds)


class SlackBot:
    """간단한 슬랙 봇 (알림용)"""
    
    def __init__(self, bot_token: str, channel_id: str):
        """
        SlackBot 초기화
        
        Args:
            bot_token: Slack Bot Token
            channel_id: 메시지를 보낼 채널 ID
        """
        self.bot_token = bot_token
        self.channel_id = channel_idㅇ
        
        # 실제 구현에서는 slack_sdk 사용
        # from slack_sdk import WebClient
        # self.client = WebClient(token=bot_token)
        
        logger.info("SlackBot 초기화 완료")
    
    def send_message(self, message: str):
        """메시지 전송 (현재는 로그로만 출력)"""
        try:
            logger.info(f"[Slack] {message}")
            
            # 실제 구현:
            # response = self.client.chat_postMessage(
            #     channel=self.channel_id,
            #     text=message
            # )
            # return response['ok']
            
            return True
            
        except Exception as e:
            logger.error(f"Slack 메시지 전송 실패: {e}")
            return False