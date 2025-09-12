#!/usr/bin/env python3
"""
로거 설정 모듈
파일 위치: src/utils/logger.py
"""

import os
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional

def setup_logger(
    name: str, 
    level: Optional[str] = None,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> logging.Logger:
    """
    로거 설정 및 반환
    
    Args:
        name: 로거 이름 (일반적으로 __name__ 사용)
        level: 로그 레벨 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_to_file: 파일 로깅 여부
        log_to_console: 콘솔 로깅 여부
    
    Returns:
        설정된 로거 객체
    """
    
    # 환경변수에서 로그 레벨 가져오기 (기본값: INFO)
    if level is None:
        level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    # 로거 생성
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 설정된 경우 중복 방지
    if logger.handlers:
        return logger
    
    # 로그 레벨 설정
    numeric_level = getattr(logging, level, logging.INFO)
    logger.setLevel(numeric_level)
    
    # 로그 포맷 설정
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 콘솔 핸들러 설정
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 파일 핸들러 설정
    if log_to_file:
        # logs 디렉토리 생성
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        # 파일명: trading_YYYYMMDD.log
        log_filename = f"trading_{datetime.now().strftime('%Y%m%d')}.log"
        log_filepath = log_dir / log_filename
        
        # 회전 로그 핸들러 (1일마다 새 파일, 최대 30개 보관)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_filepath,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    logger.info(f"로거 설정 완료 - {name} (레벨: {level})")
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    기본 설정으로 로거 반환 (간편 함수)
    
    Args:
        name: 로거 이름
    
    Returns:
        로거 객체
    """
    return setup_logger(name)


def log_function_call(logger: logging.Logger, level: str = 'DEBUG'):
    """
    함수 호출 로깅 데코레이터
    
    Args:
        logger: 로거 객체
        level: 로그 레벨
    
    Usage:
        @log_function_call(logger, 'INFO')
        def my_function():
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            log_level = getattr(logging, level.upper(), logging.DEBUG)
            logger.log(log_level, f"함수 호출: {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                logger.log(log_level, f"함수 완료: {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"함수 에러: {func.__name__} - {str(e)}")
                raise
        
        return wrapper
    return decorator


# 전역 로거 인스턴스들
_loggers = {}

def get_module_logger(module_name: str) -> logging.Logger:
    """
    모듈별 로거 반환 (캐싱)
    
    Args:
        module_name: 모듈 이름
    
    Returns:
        캐싱된 로거 객체
    """
    if module_name not in _loggers:
        _loggers[module_name] = setup_logger(module_name)
    
    return _loggers[module_name]