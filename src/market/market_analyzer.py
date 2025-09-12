#!/usr/bin/env python3
"""
시장 분석기 - 변동성과 거래량 기반 티커 추천
파일 위치: src/market/market_analyzer.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class SymbolMetrics:
    """심볼 지표 정보"""
    symbol: str
    price: float
    price_change_24h: float
    price_change_pct_24h: float
    volume_24h_usdt: float
    volume_24h_base: float
    volatility_score: float
    volume_score: float
    liquidity_score: float
    total_score: float
    rank: int = 0

@dataclass
class MarketFilter:
    """시장 필터 조건"""
    min_volume_usdt: float = 10_000_000  # 최소 일일 거래량 1천만 USDT
    min_price: float = 0.001  # 최소 가격 (너무 낮은 가격 제외)
    max_price: float = 100_000  # 최대 가격 (너무 높은 가격 제외)
    min_volatility: float = 2.0  # 최소 변동성 2%
    max_volatility: float = 30.0  # 최대 변동성 30% (너무 위험한 것 제외)
    exclude_stablecoins: bool = True  # 스테이블코인 제외
    top_n: int = 20  # 상위 N개 추천

class MarketAnalyzer:
    """시장 분석기"""
    
    def __init__(self, binance_client):
        """
        시장 분석기 초기화
        
        Args:
            binance_client: BinanceClient 인스턴스
        """
        self.binance_client = binance_client
        
        # 스테이블코인 리스트
        self.stablecoins = {
            'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 'FRAX'
        }
        
        logger.info("MarketAnalyzer 초기화 완료")
    
    def analyze_market(self, market_filter: Optional[MarketFilter] = None) -> List[SymbolMetrics]:
        """
        시장 분석 및 티커 추천
        
        Args:
            market_filter: 필터 조건
            
        Returns:
            SymbolMetrics 리스트 (점수 기준 내림차순)
        """
        try:
            if market_filter is None:
                market_filter = MarketFilter()
            
            logger.info("시장 분석 시작")
            
            # 1. 24시간 티커 데이터 조회
            ticker_data = self._get_24h_ticker_data()
            if not ticker_data:
                logger.error("티커 데이터 조회 실패")
                return []
            
            # 2. 선물 거래 가능한 심볼만 필터링
            futures_symbols = self._get_futures_symbols(ticker_data)
            logger.info(f"선물 거래 가능 심볼: {len(futures_symbols)}개")
            
            # 3. 지표 계산
            symbol_metrics = []
            for symbol_data in futures_symbols:
                metrics = self._calculate_symbol_metrics(symbol_data)
                if metrics:
                    symbol_metrics.append(metrics)
            
            # 4. 필터링 적용
            filtered_metrics = self._apply_filters(symbol_metrics, market_filter)
            logger.info(f"필터링 후 심볼: {len(filtered_metrics)}개")
            
            # 5. 점수 기반 정렬
            sorted_metrics = sorted(filtered_metrics, key=lambda x: x.total_score, reverse=True)
            
            # 6. 랭킹 부여
            for i, metrics in enumerate(sorted_metrics[:market_filter.top_n], 1):
                metrics.rank = i
            
            result = sorted_metrics[:market_filter.top_n]
            logger.info(f"시장 분석 완료: 상위 {len(result)}개 추천")
            
            return result
            
        except Exception as e:
            logger.error(f"시장 분석 실패: {e}")
            return []
    
    def _get_24h_ticker_data(self) -> List[Dict]:
        """24시간 티커 데이터 조회"""
        try:
            # 바이낸스 24시간 티커 API 호출
            # 실제 구현에서는 binance_client의 메서드 사용
            
            # 임시로 바이낸스 REST API 직접 호출
            import requests
            
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"24시간 티커 데이터 조회 완료: {len(data)}개")
                return data
            else:
                logger.error(f"티커 데이터 조회 실패: HTTP {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"24시간 티커 데이터 조회 중 에러: {e}")
            return []
    
    def _get_futures_symbols(self, ticker_data: List[Dict]) -> List[Dict]:
        """선물 거래 가능한 심볼 필터링"""
        try:
            # USDT 마진 선물만 선택
            futures_symbols = [
                data for data in ticker_data 
                if data['symbol'].endswith('USDT') and 
                float(data['count']) > 100  # 최소 거래 건수
            ]
            
            return futures_symbols
            
        except Exception as e:
            logger.error(f"선물 심볼 필터링 실패: {e}")
            return []
    
    def _calculate_symbol_metrics(self, symbol_data: Dict) -> Optional[SymbolMetrics]:
        """심볼 지표 계산"""
        try:
            symbol = symbol_data['symbol']
            price = float(symbol_data['lastPrice'])
            price_change_24h = float(symbol_data['priceChange'])
            price_change_pct_24h = float(symbol_data['priceChangePercent'])
            volume_24h_usdt = float(symbol_data['quoteVolume'])
            volume_24h_base = float(symbol_data['volume'])
            
            # 변동성 점수 (0-100)
            volatility_score = min(100, abs(price_change_pct_24h) * 3)  # 3% = 9점
            
            # 거래량 점수 (0-100) - 로그 스케일
            if volume_24h_usdt > 0:
                volume_score = min(100, np.log10(volume_24h_usdt) * 10 - 50)  # 1M = 10점
                volume_score = max(0, volume_score)
            else:
                volume_score = 0
            
            # 유동성 점수 (거래 건수 기반)
            trade_count = float(symbol_data['count'])
            liquidity_score = min(100, trade_count / 100)  # 10,000건 = 100점
            
            # 종합 점수 (가중평균)
            total_score = (
                volatility_score * 0.4 +  # 변동성 40%
                volume_score * 0.4 +      # 거래량 40%
                liquidity_score * 0.2     # 유동성 20%
            )
            
            return SymbolMetrics(
                symbol=symbol,
                price=price,
                price_change_24h=price_change_24h,
                price_change_pct_24h=price_change_pct_24h,
                volume_24h_usdt=volume_24h_usdt,
                volume_24h_base=volume_24h_base,
                volatility_score=volatility_score,
                volume_score=volume_score,
                liquidity_score=liquidity_score,
                total_score=total_score
            )
            
        except Exception as e:
            logger.warning(f"심볼 지표 계산 실패 ({symbol_data.get('symbol', 'Unknown')}): {e}")
            return None
    
    def _apply_filters(self, symbol_metrics: List[SymbolMetrics], 
                      market_filter: MarketFilter) -> List[SymbolMetrics]:
        """필터 조건 적용"""
        try:
            filtered = []
            
            for metrics in symbol_metrics:
                # 기본 필터 조건 확인
                if (metrics.volume_24h_usdt >= market_filter.min_volume_usdt and
                    market_filter.min_price <= metrics.price <= market_filter.max_price and
                    market_filter.min_volatility <= abs(metrics.price_change_pct_24h) <= market_filter.max_volatility):
                    
                    # 스테이블코인 제외 옵션
                    if market_filter.exclude_stablecoins:
                        base_asset = metrics.symbol.replace('USDT', '')
                        if base_asset in self.stablecoins:
                            continue
                    
                    filtered.append(metrics)
            
            return filtered
            
        except Exception as e:
            logger.error(f"필터 적용 실패: {e}")
            return symbol_metrics
    
    def get_symbol_analysis(self, symbol: str) -> Optional[SymbolMetrics]:
        """특정 심볼 분석"""
        try:
            logger.info(f"심볼 분석: {symbol}")
            
            # 24시간 데이터 조회
            ticker_data = self._get_24h_ticker_data()
            
            # 해당 심볼 찾기
            symbol_data = None
            for data in ticker_data:
                if data['symbol'] == symbol:
                    symbol_data = data
                    break
            
            if not symbol_data:
                logger.error(f"심볼 데이터 없음: {symbol}")
                return None
            
            # 지표 계산
            metrics = self._calculate_symbol_metrics(symbol_data)
            if metrics:
                metrics.rank = 1  # 단일 분석이므로 1위
            
            return metrics
            
        except Exception as e:
            logger.error(f"심볼 분석 실패: {e}")
            return None
    
    def generate_recommendation_report(self, symbol_metrics: List[SymbolMetrics],
                                     market_filter: MarketFilter) -> str:
        """추천 리포트 생성"""
        try:
            if not symbol_metrics:
                return "추천할 심볼이 없습니다."
            
            report = f"""
📊 **시장 분석 리포트**

**분석 조건**
• 최소 거래량: ${market_filter.min_volume_usdt:,.0f} USDT
• 변동성 범위: {market_filter.min_volatility}% ~ {market_filter.max_volatility}%
• 상위 추천: {market_filter.top_n}개

**추천 심볼** (점수 기준 내림차순)
"""
            
            for metrics in symbol_metrics:
                base_asset = metrics.symbol.replace('USDT', '')
                change_emoji = "📈" if metrics.price_change_pct_24h > 0 else "📉"
                
                report += f"""
{metrics.rank}. **{metrics.symbol}** ({base_asset}) - {metrics.total_score:.1f}점
   {change_emoji} 24시간: {metrics.price_change_pct_24h:+.2f}% (${metrics.price:.4f})
   💰 거래량: ${metrics.volume_24h_usdt:,.0f} USDT
   📊 변동성: {metrics.volatility_score:.1f}/100, 거래량: {metrics.volume_score:.1f}/100
"""
            
            return report.strip()
            
        except Exception as e:
            logger.error(f"추천 리포트 생성 실패: {e}")
            return "리포트 생성 실패"
    
    def recommend_for_strategy(self, strategy_type: str = "trend_following") -> List[str]:
        """전략 유형별 추천 심볼"""
        try:
            if strategy_type == "trend_following":
                # 트렌드 추종 전략: 중간 변동성, 높은 거래량
                market_filter = MarketFilter(
                    min_volatility=3.0,
                    max_volatility=15.0,
                    min_volume_usdt=20_000_000,
                    top_n=10
                )
            elif strategy_type == "scalping":
                # 스캘핑 전략: 높은 유동성, 적당한 변동성
                market_filter = MarketFilter(
                    min_volatility=1.0,
                    max_volatility=8.0,
                    min_volume_usdt=50_000_000,
                    top_n=5
                )
            else:
                # 기본 설정
                market_filter = MarketFilter()
            
            symbol_metrics = self.analyze_market(market_filter)
            return [metrics.symbol for metrics in symbol_metrics]
            
        except Exception as e:
            logger.error(f"전략별 추천 실패: {e}")
            return []