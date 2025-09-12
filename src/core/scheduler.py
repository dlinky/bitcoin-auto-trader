#!/usr/bin/env python3
"""
향상된 스케줄러 - NotificationManager 통합
파일 위치: src/core/scheduler.py (기존 파일 업데이트용)
"""

import schedule
import time
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable

from src.utils.logger import get_logger
from src.utils.slack_handler import setup_global_slack_logging

logger = get_logger(__name__)

class EnhancedScheduler:
    """알림 기능이 통합된 향상된 스케줄러"""
    
    def __init__(self, notification_manager=None):
        """
        스케줄러 초기화
        
        Args:
            notification_manager: NotificationManager 인스턴스 (옵션)
        """
        self.notification_manager = notification_manager
        self.is_running = False
        self.scheduler_thread = None
        
        # 등록된 작업들
        self.registered_jobs = {}
        
        # 전역 Slack 로깅 설정
        if self.notification_manager:
            self.slack_handler = setup_global_slack_logging(
                self.notification_manager, 
                level=logging.ERROR
            )
            logger.info("전역 Slack 에러 알림 활성화")
        else:
            self.slack_handler = None
            logger.warning("NotificationManager 없이 스케줄러 시작")
    
    def start(self) -> bool:
        """스케줄러 시작"""
        try:
            if self.is_running:
                logger.warning("스케줄러가 이미 실행 중입니다")
                return True
            
            logger.info("스케줄러 시작...")
            self.is_running = True
            
            # NotificationManager 시작 (있는 경우)
            if self.notification_manager:
                if not self.notification_manager.start():
                    logger.error("NotificationManager 시작 실패")
                    return False
                logger.info("NotificationManager 시작 완료")
            
            # 스케줄러 스레드 시작
            self.scheduler_thread = threading.Thread(
                target=self._run_scheduler,
                name="SchedulerThread",
                daemon=True
            )
            self.scheduler_thread.start()
            
            logger.info("스케줄러 시작 완료")
            
            # 시작 알림 전송
            if self.notification_manager:
                self.notification_manager.send_system_status({
                    'system_status': 'started',
                    'uptime': '방금 시작됨',
                    'active_traders': 0,
                    'last_trade': 'N/A',
                    'errors_today': 0
                })
            
            return True
            
        except Exception as e:
            logger.error(f"스케줄러 시작 실패: {e}")
            return False
    
    def stop(self):
        """스케줄러 정지"""
        try:
            if not self.is_running:
                logger.info("스케줄러가 이미 정지된 상태입니다")
                return
            
            logger.info("스케줄러 정지 중...")
            
            # 정지 알림 전송
            if self.notification_manager:
                self.notification_manager.send_system_status({
                    'system_status': 'stopping',
                    'uptime': '정지 중',
                    'active_traders': 0,
                    'last_trade': 'N/A',
                    'errors_today': 0
                })
            
            self.is_running = False
            
            # 스케줄 초기화
            schedule.clear()
            
            # 스레드 종료 대기
            if self.scheduler_thread and self.scheduler_thread.is_alive():
                self.scheduler_thread.join(timeout=5)
            
            # NotificationManager 정지
            if self.notification_manager:
                self.notification_manager.stop()
            
            logger.info("스케줄러 정지 완료")
            
        except Exception as e:
            logger.error(f"스케줄러 정지 중 에러: {e}")
    
    def _run_scheduler(self):
        """스케줄러 메인 루프"""
        logger.info("스케줄러 루프 시작")
        
        while self.is_running:
            try:
                # 대기 중인 작업 실행
                schedule.run_pending()
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"스케줄러 루프 에러: {e}")
                # 에러 발생 시 알림은 자동으로 Slack으로 전송됨 (SlackHandler)
                time.sleep(5)
        
        logger.info("스케줄러 루프 종료")
    
    def add_job(self, name: str, job_func: Callable, schedule_time: str, 
                job_type: str = "daily", **kwargs) -> bool:
        """
        작업 추가
        
        Args:
            name: 작업 이름
            job_func: 실행할 함수
            schedule_time: 스케줄 시간 ("HH:MM" 형식)
            job_type: 작업 유형 ("daily", "hourly", "minutes")
            **kwargs: job_func에 전달할 추가 인자
            
        Returns:
            작업 추가 성공 여부
        """
        try:
            # 래퍼 함수 생성 (에러 처리 및 알림 포함)
            def job_wrapper():
                job_start_time = datetime.now()
                job_name = name
                
                try:
                    logger.info(f"작업 시작: {job_name}")
                    
                    # 실제 작업 실행
                    result = job_func(**kwargs)
                    
                    # 작업 완료 로그
                    elapsed_time = (datetime.now() - job_start_time).total_seconds()
                    logger.info(f"작업 완료: {job_name} ({elapsed_time:.1f}초)")
                    
                    return result
                    
                except Exception as e:
                    # 작업 에러는 자동으로 Slack 알림됨 (SlackHandler)
                    elapsed_time = (datetime.now() - job_start_time).total_seconds()
                    logger.error(f"작업 실패: {job_name} ({elapsed_time:.1f}초) - {e}")
                    raise
            
            # 스케줄 등록
            if job_type == "daily":
                schedule.every().day.at(schedule_time).do(job_wrapper)
            elif job_type == "hourly":
                schedule.every().hour.at(f":{schedule_time}").do(job_wrapper)  # :MM 형식
            elif job_type == "minutes":
                interval = int(schedule_time)
                schedule.every(interval).minutes.do(job_wrapper)
            else:
                raise ValueError(f"지원하지 않는 작업 유형: {job_type}")
            
            # 등록된 작업 기록
            self.registered_jobs[name] = {
                'function': job_func,
                'schedule_time': schedule_time,
                'job_type': job_type,
                'kwargs': kwargs,
                'registered_at': datetime.now().isoformat()
            }
            
            logger.info(f"작업 등록 완료: {name} ({job_type} {schedule_time})")
            return True
            
        except Exception as e:
            logger.error(f"작업 등록 실패: {name} - {e}")
            return False
    
    def add_data_collection_job(self, data_collector, symbols: List[str]):
        """데이터 수집 작업 추가 (매분 0초)"""
        def collect_data():
            return data_collector.collect_all_symbols_concurrent()
        
        return self.add_job(
            name="data_collection",
            job_func=collect_data,
            schedule_time="1",  # 매 1분마다
            job_type="minutes"
        )
    
    def add_trading_job(self, traders: List):
        """트레이딩 작업 추가 (매분 실행)"""
        def execute_trading():
            results = {}
            for trader in traders:
                try:
                    result = trader.execute_trading_cycle()
                    results[trader.trader_id] = result
                except Exception as e:
                    logger.error(f"트레이더 {trader.trader_id} 실행 실패: {e}")
                    results[trader.trader_id] = {'success': False, 'reason': str(e)}
            
            return results
        
        return self.add_job(
            name="trading_execution",
            job_func=execute_trading,
            schedule_time="1",  # 매 1분마다  
            job_type="minutes"
        )
    
    def add_system_status_job(self, interval_minutes: int = 60):
        """시스템 상태 알림 작업 추가"""
        if not self.notification_manager:
            logger.warning("NotificationManager 없이 시스템 상태 작업 추가 불가")
            return False
        
        def send_status():
            return self.notification_manager.send_system_status()
        
        return self.add_job(
            name="system_status_report",
            job_func=send_status,
            schedule_time=str(interval_minutes),
            job_type="minutes"
        )
    
    def remove_job(self, name: str) -> bool:
        """작업 제거"""
        try:
            if name in self.registered_jobs:
                # 스케줄에서 해당 작업 제거는 복잡하므로 전체 재등록 필요
                # 현재는 로그만 기록
                del self.registered_jobs[name]
                logger.info(f"작업 제거됨: {name}")
                return True
            else:
                logger.warning(f"존재하지 않는 작업: {name}")
                return False
                
        except Exception as e:
            logger.error(f"작업 제거 실패: {name} - {e}")
            return False
    
    def get_job_status(self) -> Dict:
        """작업 상태 조회"""
        return {
            'is_running': self.is_running,
            'notification_manager_connected': self.notification_manager is not None,
            'slack_handler_active': self.slack_handler is not None,
            'registered_jobs': len(self.registered_jobs),
            'jobs_detail': self.registered_jobs,
            'next_runs': [str(job) for job in schedule.jobs] if schedule.jobs else []
        }
    
    def send_test_notification(self) -> bool:
        """테스트 알림 전송"""
        if not self.notification_manager:
            logger.error("NotificationManager가 없어서 테스트 알림 전송 불가")
            return False
        
        try:
            # 에러 알림 테스트
            self.notification_manager.send_error_alert(
                "스케줄러 테스트 알림",
                "enhanced_scheduler",
                "INFO",
                {
                    "test_type": "scheduler_test",
                    "timestamp": datetime.now().isoformat(),
                    "registered_jobs": len(self.registered_jobs)
                }
            )
            
            # 시스템 상태 테스트
            self.notification_manager.send_system_status({
                'system_status': 'testing',
                'uptime': '테스트 모드',
                'active_traders': len(self.registered_jobs),
                'last_trade': 'N/A',
                'errors_today': 0
            })
            
            logger.info("테스트 알림 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"테스트 알림 전송 실패: {e}")
            return False