#!/usr/bin/env python3
"""
알림 관리 시스템
파일 위치: src/core/notification_manager.py
"""

import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from queue import Queue, Empty

from src.utils.logger import get_logger
from src.api.slack_client import SlackClient

logger = get_logger(__name__)

class NotificationManager:
    """알림 관리자 - Slack 알림 및 스케줄링 총괄"""
    
    def __init__(self, supabase_client):
        """
        NotificationManager 초기화
        
        Args:
            supabase_client: SupabaseClient 인스턴스 (트레이더 정보 조회용)
        """
        self.db_client = supabase_client
        self.slack_client = None
        
        # 알림 큐 (비동기 처리용)
        self.notification_queue = Queue()
        
        # 스레드 관리
        self.notification_thread = None
        self.is_running = False
        
        # 일일 리포트 스케줄링
        self.daily_report_time = "07:00"  # 매일 07시
        self.last_report_date = None
        
        # 에러 알림 제한 (스팸 방지)
        self.error_throttle = {}  # {error_key: last_sent_time}
        self.error_throttle_seconds = 300  # 5분 간격
        
        logger.info("NotificationManager 초기화 완료")
    
    def initialize_slack(self) -> bool:
        """
        Slack 클라이언트 초기화
        
        Returns:
            초기화 성공 여부
        """
        try:
            self.slack_client = SlackClient()
            logger.info("Slack 클라이언트 연동 완료")
            return True
            
        except Exception as e:
            logger.error(f"Slack 클라이언트 초기화 실패: {e}")
            return False
    
    def start(self) -> bool:
        """
        알림 관리자 시작 (백그라운드 스레드 시작)
        
        Returns:
            시작 성공 여부
        """
        try:
            if self.is_running:
                logger.warning("NotificationManager가 이미 실행 중입니다")
                return True
            
            # Slack 클라이언트 초기화
            if not self.initialize_slack():
                logger.error("Slack 초기화 실패로 NotificationManager 시작 불가")
                return False
            
            self.is_running = True
            
            # 백그라운드 스레드 시작
            self.notification_thread = threading.Thread(
                target=self._notification_worker,
                name="NotificationWorker",
                daemon=True
            )
            self.notification_thread.start()
            
            logger.info("NotificationManager 시작 완료")
            return True
            
        except Exception as e:
            logger.error(f"NotificationManager 시작 실패: {e}")
            return False
    
    def stop(self):
        """알림 관리자 정지"""
        try:
            if not self.is_running:
                logger.info("NotificationManager가 이미 정지된 상태입니다")
                return
            
            logger.info("NotificationManager 정지 중...")
            self.is_running = False
            
            # 스레드 종료 대기 (최대 5초)
            if self.notification_thread and self.notification_thread.is_alive():
                self.notification_thread.join(timeout=5)
            
            logger.info("NotificationManager 정지 완료")
            
        except Exception as e:
            logger.error(f"NotificationManager 정지 중 에러: {e}")
    
    def _notification_worker(self):
        """백그라운드 알림 처리 스레드"""
        logger.info("알림 처리 스레드 시작")
        
        last_daily_check = datetime.now()
        
        while self.is_running:
            try:
                # 1. 큐에서 알림 처리
                self._process_notification_queue()
                
                # 2. 일일 리포트 스케줄 확인 (1분마다)
                now = datetime.now()
                if (now - last_daily_check).total_seconds() >= 60:
                    self._check_daily_report_schedule()
                    last_daily_check = now
                
                # 3. 잠시 대기
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"알림 처리 스레드 에러: {e}")
                time.sleep(5)  # 에러 시 5초 대기
        
        logger.info("알림 처리 스레드 종료")
    
    def _process_notification_queue(self):
        """알림 큐 처리"""
        try:
            while not self.notification_queue.empty():
                try:
                    # 큐에서 알림 가져오기 (1초 타임아웃)
                    notification = self.notification_queue.get(timeout=1)
                    
                    # 알림 타입에 따른 처리
                    if notification['type'] == 'error':
                        self._send_error_notification(notification)
                    elif notification['type'] == 'daily_report':
                        self._send_daily_report_notification(notification)
                    elif notification['type'] == 'system_status':
                        self._send_system_status_notification(notification)
                    else:
                        logger.warning(f"알 수 없는 알림 타입: {notification['type']}")
                    
                    # 큐 작업 완료 표시
                    self.notification_queue.task_done()
                    
                except Empty:
                    # 큐가 비어있으면 루프 종료
                    break
                except Exception as e:
                    logger.error(f"알림 처리 중 에러: {e}")
                    
        except Exception as e:
            logger.error(f"알림 큐 처리 중 에러: {e}")
    
    def _check_daily_report_schedule(self):
        """일일 리포트 스케줄 확인"""
        try:
            now = datetime.now()
            current_date = now.strftime('%Y-%m-%d')
            current_time = now.strftime('%H:%M')
            
            # 이미 오늘 리포트를 보냈는지 확인
            if self.last_report_date == current_date:
                return
            
            # 07:00 시간 확인 (±1분 허용)
            target_hour, target_minute = map(int, self.daily_report_time.split(':'))
            current_hour, current_minute = now.hour, now.minute
            
            # 07:00~07:01 사이에 실행
            if (current_hour == target_hour and 
                target_minute <= current_minute <= target_minute + 1):
                
                logger.info("일일 리포트 시간 - 리포트 생성 시작")
                self.send_daily_report()
                self.last_report_date = current_date
                
        except Exception as e:
            logger.error(f"일일 리포트 스케줄 확인 중 에러: {e}")
    
    def send_error_alert(self, error_message: str, module_name: str = "Unknown", 
                        level: str = "ERROR", additional_info: Optional[Dict] = None,
                        throttle: bool = True) -> bool:
        """
        에러 알림 전송 (비동기)
        
        Args:
            error_message: 에러 메시지
            module_name: 발생 모듈명
            level: 에러 레벨
            additional_info: 추가 정보
            throttle: 스팸 방지 활성화 여부
            
        Returns:
            큐 추가 성공 여부
        """
        try:
            # 스팸 방지 (동일 에러를 5분 내에 중복 전송 방지)
            if throttle:
                error_key = f"{module_name}:{error_message[:50]}"
                now = time.time()
                
                if error_key in self.error_throttle:
                    last_sent = self.error_throttle[error_key]
                    if now - last_sent < self.error_throttle_seconds:
                        logger.debug(f"에러 알림 스팸 방지: {error_key}")
                        return False
                
                self.error_throttle[error_key] = now
            
            # 알림 큐에 추가
            notification = {
                'type': 'error',
                'timestamp': datetime.now().isoformat(),
                'error_message': error_message,
                'module_name': module_name,
                'level': level,
                'additional_info': additional_info
            }
            
            self.notification_queue.put(notification)
            logger.debug(f"에러 알림 큐 추가: {module_name} - {level}")
            return True
            
        except Exception as e:
            logger.error(f"에러 알림 큐 추가 실패: {e}")
            return False
    
    def send_daily_report(self, force: bool = False) -> bool:
        """
        일일 리포트 전송 (비동기)
        
        Args:
            force: 강제 전송 여부 (스케줄 무시)
            
        Returns:
            큐 추가 성공 여부
        """
        try:
            notification = {
                'type': 'daily_report',
                'timestamp': datetime.now().isoformat(),
                'force': force
            }
            
            self.notification_queue.put(notification)
            logger.info("일일 리포트 큐 추가")
            return True
            
        except Exception as e:
            logger.error(f"일일 리포트 큐 추가 실패: {e}")
            return False
    
    def send_system_status(self, status_data: Optional[Dict] = None) -> bool:
        """
        시스템 상태 전송 (비동기)
        
        Args:
            status_data: 상태 데이터 (None이면 자동 수집)
            
        Returns:
            큐 추가 성공 여부
        """
        try:
            notification = {
                'type': 'system_status',
                'timestamp': datetime.now().isoformat(),
                'status_data': status_data
            }
            
            self.notification_queue.put(notification)
            logger.info("시스템 상태 큐 추가")
            return True
            
        except Exception as e:
            logger.error(f"시스템 상태 큐 추가 실패: {e}")
            return False
    
    def _send_error_notification(self, notification: Dict):
        """에러 알림 실제 전송"""
        try:
            if not self.slack_client:
                logger.error("Slack 클라이언트가 없어서 에러 알림 전송 불가")
                return
            
            success = self.slack_client.send_error_alert(
                error_message=notification['error_message'],
                module_name=notification['module_name'],
                level=notification['level'],
                additional_info=notification.get('additional_info')
            )
            
            if success:
                logger.debug(f"에러 알림 전송 완료: {notification['module_name']}")
            else:
                logger.error(f"에러 알림 전송 실패: {notification['module_name']}")
                
        except Exception as e:
            logger.error(f"에러 알림 전송 중 에러: {e}")
    
    def _send_daily_report_notification(self, notification: Dict):
        """일일 리포트 실제 전송"""
        try:
            if not self.slack_client:
                logger.error("Slack 클라이언트가 없어서 일일 리포트 전송 불가")
                return
            
            # 리포트 데이터 생성
            report_data = self._generate_daily_report_data()
            
            success = self.slack_client.send_daily_report(report_data)
            
            if success:
                logger.info("일일 리포트 전송 완료")
            else:
                logger.error("일일 리포트 전송 실패")
                
        except Exception as e:
            logger.error(f"일일 리포트 전송 중 에러: {e}")
    
    def _send_system_status_notification(self, notification: Dict):
        """시스템 상태 실제 전송"""
        try:
            if not self.slack_client:
                logger.error("Slack 클라이언트가 없어서 시스템 상태 전송 불가")
                return
            
            # 상태 데이터 준비
            status_data = notification.get('status_data')
            if not status_data:
                status_data = self._generate_system_status_data()
            
            success = self.slack_client.send_system_status(status_data)
            
            if success:
                logger.info("시스템 상태 전송 완료")
            else:
                logger.error("시스템 상태 전송 실패")
                
        except Exception as e:
            logger.error(f"시스템 상태 전송 중 에러: {e}")
    
    def _generate_daily_report_data(self) -> Dict:
        """일일 리포트 데이터 생성"""
        try:
            # 어제 날짜 계산
            yesterday = datetime.now() - timedelta(days=1)
            report_date = yesterday.strftime('%Y-%m-%d')
            
            # 활성 트레이더 목록 조회
            active_traders = self.db_client.get_active_traders()
            
            traders_data = []
            total_pnl = 0.0
            total_trades = 0
            
            for trader in active_traders:
                trader_id = trader['id']
                trader_name = trader['name']
                symbol = trader['symbol']
                
                # 어제 거래 내역 조회
                trades = self._get_trader_trades_by_date(trader_id, report_date)
                trades_count = len(trades)
                
                # 성공률 계산 (간단히 실현 손익이 양수인 비율)
                successful_trades = len([t for t in trades if t.get('realized_pnl', 0) > 0])
                success_rate = (successful_trades / trades_count * 100) if trades_count > 0 else 0
                
                # 트레이더 총 손익
                trader_pnl = trader.get('total_pnl', 0.0) or 0.0
                
                traders_data.append({
                    'name': trader_name,
                    'symbol': symbol,
                    'total_pnl': trader_pnl,
                    'trades_count': trades_count,
                    'success_rate': success_rate
                })
                
                total_pnl += trader_pnl
                total_trades += trades_count
            
            return {
                'date': report_date,
                'traders': traders_data,
                'total_pnl': total_pnl,
                'total_trades': total_trades
            }
            
        except Exception as e:
            logger.error(f"일일 리포트 데이터 생성 실패: {e}")
            return {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'traders': [],
                'total_pnl': 0.0,
                'total_trades': 0,
                'error': f"데이터 생성 실패: {str(e)}"
            }
    
    def _generate_system_status_data(self) -> Dict:
        """시스템 상태 데이터 생성"""
        try:
            # 활성 트레이더 수
            active_traders = self.db_client.get_active_traders()
            active_count = len(active_traders)
            
            # 마지막 거래 시간 조회 (최근 24시간)
            last_trade_time = self._get_last_trade_time()
            
            # 오늘 에러 수 조회
            errors_today = self._get_today_error_count()
            
            return {
                'system_status': 'running',
                'uptime': 'N/A',  # 추후 구현
                'active_traders': active_count,
                'last_trade': last_trade_time,
                'errors_today': errors_today
            }
            
        except Exception as e:
            logger.error(f"시스템 상태 데이터 생성 실패: {e}")
            return {
                'system_status': 'error',
                'uptime': 'N/A',
                'active_traders': 0,
                'last_trade': 'N/A',
                'errors_today': 0,
                'error': f"상태 조회 실패: {str(e)}"
            }
    
    def _get_trader_trades_by_date(self, trader_id: int, date: str) -> List[Dict]:
        """특정 날짜의 트레이더 거래 내역 조회"""
        try:
            response = self.db_client.client.table('trades').select('*').eq(
                'trader_id', trader_id
            ).gte(
                'executed_at', f'{date}T00:00:00'
            ).lt(
                'executed_at', f'{date}T23:59:59'
            ).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"트레이더 거래 내역 조회 실패 (ID: {trader_id}, 날짜: {date}): {e}")
            return []
    
    def _get_last_trade_time(self) -> str:
        """최근 거래 시간 조회"""
        try:
            response = self.db_client.client.table('trades').select(
                'executed_at'
            ).order(
                'executed_at', desc=True
            ).limit(1).execute()
            
            if response.data:
                return response.data[0]['executed_at']
            else:
                return 'N/A'
                
        except Exception as e:
            logger.error(f"최근 거래 시간 조회 실패: {e}")
            return 'N/A'
    
    def _get_today_error_count(self) -> int:
        """오늘 에러 수 조회"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            response = self.db_client.client.table('system_logs').select(
                'id', count='exact'
            ).eq(
                'level', 'ERROR'
            ).gte(
                'created_at', f'{today}T00:00:00'
            ).execute()
            
            return response.count or 0
            
        except Exception as e:
            logger.error(f"오늘 에러 수 조회 실패: {e}")
            return 0
    
    def get_notification_status(self) -> Dict:
        """알림 시스템 상태 조회"""
        return {
            'is_running': self.is_running,
            'slack_connected': self.slack_client is not None,
            'queue_size': self.notification_queue.qsize(),
            'last_report_date': self.last_report_date,
            'daily_report_time': self.daily_report_time,
            'error_throttle_count': len(self.error_throttle)
        }
    
    def set_daily_report_time(self, time_str: str) -> bool:
        """
        일일 리포트 시간 설정
        
        Args:
            time_str: "HH:MM" 형식 시간
            
        Returns:
            설정 성공 여부
        """
        try:
            # 시간 형식 검증
            hour, minute = map(int, time_str.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("잘못된 시간 형식")
            
            self.daily_report_time = time_str
            logger.info(f"일일 리포트 시간 변경: {time_str}")
            return True
            
        except Exception as e:
            logger.error(f"일일 리포트 시간 설정 실패: {e}")
            return False