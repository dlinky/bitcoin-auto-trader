#!/usr/bin/env python3
"""
Slack Logging Handler - 로그를 Slack으로 실시간 전송
파일 위치: src/utils/slack_handler.py
"""

import logging
import traceback
from typing import Optional

class SlackHandler(logging.Handler):
    """로그를 Slack으로 전송하는 핸들러"""
    
    def __init__(self, notification_manager, level=logging.WARNING):
        """
        SlackHandler 초기화
        
        Args:
            notification_manager: NotificationManager 인스턴스
            level: 최소 로그 레벨 (기본: WARNING)
        """
        super().__init__(level)
        self.notification_manager = notification_manager
        self.setLevel(level)
        
        # 로그 포맷 설정 (간단한 포맷)
        formatter = logging.Formatter('%(message)s')
        self.setFormatter(formatter)
    
    def emit(self, record):
        """로그 레코드 처리 (Slack으로 전송)"""
        try:
            # 전송할 레벨 확인
            if record.levelno < self.level:
                return
            
            # 로그 메시지 생성
            message = self.format(record)
            
            # 모듈명 추출
            module_name = record.name if record.name else "Unknown"
            
            # 추가 정보 생성
            additional_info = {
                'logger': record.name,
                'function': record.funcName,
                'line': record.lineno,
                'thread': record.thread,
                'process': record.process
            }
            
            # 예외 정보가 있는 경우 추가
            if record.exc_info:
                additional_info['exception'] = ''.join(
                    traceback.format_exception(*record.exc_info)
                )
            
            # NotificationManager를 통해 에러 알림 전송
            if self.notification_manager and self.notification_manager.is_running:
                self.notification_manager.send_error_alert(
                    error_message=message,
                    module_name=module_name,
                    level=record.levelname,
                    additional_info=additional_info,
                    throttle=True  # 스팸 방지 활성화
                )
                
        except Exception as e:
            # Slack 전송 실패 시 콘솔에 에러 출력 (무한 루프 방지)
            print(f"SlackHandler 에러: {e}")
            print(f"원본 로그: {record.getMessage()}")
    
    def close(self):
        """핸들러 정리"""
        super().close()


def add_slack_handler_to_logger(logger, notification_manager, level=logging.WARNING):
    """
    기존 로거에 Slack Handler 추가
    
    Args:
        logger: 로거 객체
        notification_manager: NotificationManager 인스턴스  
        level: 최소 로그 레벨
    """
    slack_handler = SlackHandler(notification_manager, level)
    logger.addHandler(slack_handler)
    return slack_handler


def setup_global_slack_logging(notification_manager, level=logging.ERROR):
    """
    전역 로깅에 Slack Handler 추가
    
    Args:
        notification_manager: NotificationManager 인스턴스
        level: 최소 로그 레벨 (기본: ERROR만 Slack 전송)
    """
    # 루트 로거에 Slack Handler 추가
    root_logger = logging.getLogger()
    slack_handler = SlackHandler(notification_manager, level)
    root_logger.addHandler(slack_handler)
    
    return slack_handler