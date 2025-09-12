"""
백테스트 실행기 - 모든 백테스팅 컴포넌트 통합
파일 위치: run_backtest.py
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 프로젝트 루트 경로 설정
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.api.supabase_client import SupabaseClient
from src.api.slack_client import SlackClient
from src.strategies.macd_atr import MACDATRStrategy
from src.backtesting.backtester import Backtester
from src.backtesting.performance_analyzer import PerformanceAnalyzer
from src.backtesting.backtest_reporter import BacktestReporter
from src.utils.logger import get_logger

logger = get_logger(__name__)

class BacktestRunner:
    """백테스트 실행 통합 관리자"""
    
    def __init__(self):
        """백테스트 실행기 초기화"""
        self.supabase_client = None
        self.slack_client = None
        self.strategies = {
            'MACD_ATR': MACDATRStrategy
        }
        
        logger.info("BacktestRunner 초기화")
    
    def initialize(self) -> bool:
        """초기화"""
        try:
            # 환경변수 로드
            env_path = project_root / 'config' / '.env'
            if env_path.exists():
                load_dotenv(env_path)
                logger.info("환경변수 로드 완료")
            
            # Supabase 클라이언트 초기화
            self.supabase_client = SupabaseClient()
            logger.info("Supabase 연결 완료")
            
            # Slack 클라이언트 초기화 (선택사항)
            try:
                self.slack_client = SlackClient()
                logger.info("Slack 연결 완료")
            except Exception as e:
                logger.warning(f"Slack 연결 실패 (선택사항): {e}")
                self.slack_client = None
            
            return True
            
        except Exception as e:
            logger.error(f"초기화 실패: {e}")
            return False
    
    def get_market_data(self, symbol: str, days: int = 30) -> 'pd.DataFrame':
        """
        시장 데이터 조회 (부족한 데이터 자동 보완)
        
        Args:
            symbol: 거래 심볼
            days: 조회할 일수
            
        Returns:
            시장 데이터 DataFrame
        """
        try:
            logger.info(f"{symbol} 시장 데이터 조회 ({days}일)")
            
            # 1. DB에서 기존 데이터 조회
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            response = self.supabase_client.client.table('market_data').select('*').eq(
                'symbol', symbol
            ).gte(
                'timestamp', start_time.isoformat()
            ).lte(
                'timestamp', end_time.isoformat()
            ).order('timestamp', desc=False).execute()
            
            # 2. 데이터 충분성 검사
            required_count = days * 24 * 60  # 분봉 기준 예상 개수
            actual_count = len(response.data) if response.data else 0
            
            logger.info(f"{symbol} 기존 데이터: {actual_count}개 (필요: {required_count}개)")
            
            # 3. 데이터 부족하면 자동 수집
            if actual_count < required_count * 0.8:  # 80% 이하면 부족으로 판단
                logger.info(f"{symbol} 데이터 부족, 자동 수집 시작...")
                
                if self._collect_missing_data(symbol, days):
                    # 데이터 수집 후 재조회
                    response = self.supabase_client.client.table('market_data').select('*').eq(
                        'symbol', symbol
                    ).gte(
                        'timestamp', start_time.isoformat()
                    ).lte(
                        'timestamp', end_time.isoformat()
                    ).order('timestamp', desc=False).execute()
                    
                    logger.info(f"{symbol} 데이터 수집 완료: {len(response.data)}개")
                else:
                    logger.warning(f"{symbol} 데이터 수집 실패, 기존 데이터로 진행")
            
            if not response.data:
                logger.error(f"{symbol} 데이터가 없습니다")
                return None
            
            # 4. DataFrame 변환
            import pandas as pd
            df = pd.DataFrame(response.data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            logger.info(f"{symbol} 데이터 조회 완료: {len(df)}개 레코드")
            return df
            
        except Exception as e:
            logger.error(f"시장 데이터 조회 실패: {e}")
            return None
    
    def _collect_missing_data(self, symbol: str, days: int) -> bool:
        """부족한 데이터 자동 수집"""
        try:
            import requests
            import pandas as pd
            import pandas_ta as ta
            import time
            
            logger.info(f"{symbol} 과거 데이터 수집 시작...")
            
            # 바이낸스 API로 데이터 수집
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # 바이낸스 선물 API 엔드포인트
            base_url = "https://fapi.binance.com"
            
            all_klines = []
            current_start = start_time
            
            # 배치로 데이터 수집 (한 번에 최대 1500개)
            max_limit = 1500
            
            while current_start < end_time:
                # API 호출 제한 준수
                time.sleep(0.1)  # 100ms 대기
                
                # 배치 종료 시간 계산
                batch_end = min(current_start + timedelta(minutes=max_limit-1), end_time)
                
                # 타임스탬프 변환
                start_ts = int(current_start.timestamp() * 1000)
                end_ts = int(batch_end.timestamp() * 1000)
                
                url = f"{base_url}/fapi/v1/klines"
                params = {
                    'symbol': symbol,
                    'interval': '1m',
                    'startTime': start_ts,
                    'endTime': end_ts,
                    'limit': max_limit
                }
                
                logger.debug(f"배치 수집: {current_start.strftime('%Y-%m-%d %H:%M')} ~ {batch_end.strftime('%Y-%m-%d %H:%M')}")
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code != 200:
                    logger.error(f"바이낸스 API 호출 실패: HTTP {response.status_code}")
                    if response.status_code == 429:  # Rate limit
                        time.sleep(60)  # 1분 대기
                        continue
                    return False
                
                klines = response.json()
                
                if not klines:
                    break
                
                # 데이터 변환
                for kline in klines:
                    timestamp = datetime.fromtimestamp(kline[0] / 1000)
                    
                    kline_data = {
                        'symbol': symbol,
                        'timestamp': timestamp,
                        'open': float(kline[1]),
                        'high': float(kline[2]),
                        'low': float(kline[3]),
                        'close': float(kline[4]),
                        'volume': float(kline[5])
                    }
                    
                    all_klines.append(kline_data)
                
                # 다음 배치 시작점 설정
                if klines:
                    last_timestamp = datetime.fromtimestamp(klines[-1][0] / 1000)
                    current_start = last_timestamp + timedelta(minutes=1)
                else:
                    break
            
            if not all_klines:
                logger.error(f"{symbol} 바이낸스에서 데이터를 가져올 수 없습니다")
                return False
            
            logger.info(f"{symbol} 바이낸스에서 {len(all_klines)}개 수집")
            
            # 지표 계산
            if len(all_klines) >= 50:
                df = pd.DataFrame(all_klines)
                
                # MACD 계산
                macd = df.ta.macd(fast=12, slow=26, signal=9)
                atr = df.ta.atr(length=14)
                
                # 지표 데이터 추가
                for i, kline_data in enumerate(all_klines):
                    # MACD 값들 추가
                    if macd is not None and len(macd.columns) >= 3 and i < len(macd):
                        macd_line = macd.iloc[i, 0] if not pd.isna(macd.iloc[i, 0]) else None
                        macd_histogram = macd.iloc[i, 1] if not pd.isna(macd.iloc[i, 1]) else None
                        macd_signal = macd.iloc[i, 2] if not pd.isna(macd.iloc[i, 2]) else None
                        
                        if macd_line is not None:
                            kline_data['macd_12_26_9_line'] = float(macd_line)
                        if macd_histogram is not None:
                            kline_data['macd_12_26_9_histogram'] = float(macd_histogram)
                        if macd_signal is not None:
                            kline_data['macd_12_26_9_signal'] = float(macd_signal)
                    
                    # ATR 값 추가
                    if atr is not None and i < len(atr) and not pd.isna(atr.iloc[i]):
                        kline_data['atr_14_value'] = float(atr.iloc[i])
            
            # DB에 배치 저장
            batch_size = 1000
            for i in range(0, len(all_klines), batch_size):
                batch = all_klines[i:i + batch_size]
                
                try:
                    response = self.supabase_client.client.table('market_data').upsert(
                        batch, on_conflict='symbol,timestamp'
                    ).execute()
                    
                    logger.debug(f"배치 저장 완료: {len(batch)}개")
                    
                except Exception as e:
                    logger.warning(f"배치 저장 실패: {e}")
                
                # DB 부하 방지
                time.sleep(0.1)
            
            logger.info(f"{symbol} 데이터 수집 및 저장 완료")
            return True
            
        except Exception as e:
            logger.error(f"{symbol} 데이터 수집 실패: {e}")
            return False
    
    def run_single_backtest(self, strategy_name: str, symbol: str = 'BTCUSDT', 
                           days: int = 30, initial_capital: float = 10000.0,
                           send_to_slack: bool = True) -> 'BacktestResult':
        """
        단일 전략 백테스트 실행
        
        Args:
            strategy_name: 전략 이름
            symbol: 거래 심볼
            days: 백테스트 기간 (일)
            initial_capital: 초기 자본
            send_to_slack: Slack 전송 여부
            
        Returns:
            BacktestResult 객체
        """
        try:
            logger.info(f"백테스트 시작: {strategy_name} - {symbol} ({days}일)")
            
            # 전략 확인
            if strategy_name not in self.strategies:
                raise ValueError(f"지원하지 않는 전략: {strategy_name}")
            
            # 시장 데이터 조회
            market_data = self.get_market_data(symbol, days)
            if market_data is None or market_data.empty:
                raise ValueError("시장 데이터를 가져올 수 없습니다")
            
            # 전략 인스턴스 생성
            strategy_class = self.strategies[strategy_name]

            # 백테스팅에서는 supabase_client 없이 전략 생성
            try:
                # supabase_client 없이 초기화 시도
                strategy = strategy_class()
            except TypeError:
                # supabase_client가 필요한 경우 전달
                strategy = strategy_class(self.supabase_client)
            
            # 백테스터 생성 및 실행
            backtester = Backtester(initial_capital=initial_capital)
            result = backtester.run_backtest(strategy, market_data, symbol)
            
            # 결과 리포트
            self._print_result_summary(result)
            
            # Slack 전송
            if send_to_slack and self.slack_client:
                reporter = BacktestReporter(self.slack_client)
                reporter.send_backtest_report(result, include_charts=True)
            
            # 파일 저장
            self._save_result_to_file(result)
            
            logger.info("백테스트 완료")
            return result
            
        except Exception as e:
            logger.error(f"백테스트 실행 실패: {e}")
            raise
    
    def run_strategy_comparison(self, strategies: list, symbol: str = 'BTCUSDT',
                              days: int = 30, initial_capital: float = 10000.0,
                              send_to_slack: bool = True) -> list:
        """
        여러 전략 비교 백테스트
        
        Args:
            strategies: 전략 이름 리스트
            symbol: 거래 심볼
            days: 백테스트 기간
            initial_capital: 초기 자본
            send_to_slack: Slack 전송 여부
            
        Returns:
            BacktestResult 리스트
        """
        try:
            logger.info(f"전략 비교 백테스트 시작: {strategies}")
            
            results = []
            
            # 각 전략별 백테스트 실행
            for strategy_name in strategies:
                logger.info(f"전략 실행 중: {strategy_name}")
                
                result = self.run_single_backtest(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    days=days,
                    initial_capital=initial_capital,
                    send_to_slack=False  # 개별 전송 비활성화
                )
                
                results.append(result)
            
            # 비교 리포트 출력
            self._print_comparison_summary(results)
            
            # Slack 비교 리포트 전송
            if send_to_slack and self.slack_client:
                reporter = BacktestReporter(self.slack_client)
                reporter.send_comparison_report(results)
            
            logger.info("전략 비교 백테스트 완료")
            return results
            
        except Exception as e:
            logger.error(f"전략 비교 백테스트 실패: {e}")
            raise
    
    def run_parameter_optimization(self, strategy_name: str, 
                                  parameter_ranges: dict, symbol: str = 'BTCUSDT',
                                  days: int = 30, initial_capital: float = 10000.0) -> list:
        """
        파라미터 최적화 백테스트
        
        Args:
            strategy_name: 전략 이름
            parameter_ranges: 파라미터 범위 딕셔너리
            symbol: 거래 심볼
            days: 백테스트 기간
            initial_capital: 초기 자본
            
        Returns:
            최적화 결과 리스트
        """
        try:
            logger.info(f"파라미터 최적화 시작: {strategy_name}")
            
            # 파라미터 조합 생성
            import itertools
            
            param_names = list(parameter_ranges.keys())
            param_values = list(parameter_ranges.values())
            param_combinations = list(itertools.product(*param_values))
            
            logger.info(f"총 {len(param_combinations)}개 조합 테스트")
            
            optimization_results = []
            
            # 시장 데이터 미리 조회 (성능 향상)
            market_data = self.get_market_data(symbol, days)
            if market_data is None:
                raise ValueError("시장 데이터를 가져올 수 없습니다")
            
            # 각 파라미터 조합별 백테스트
            for i, param_combo in enumerate(param_combinations, 1):
                logger.info(f"조합 {i}/{len(param_combinations)} 테스트 중...")
                
                try:
                    # 파라미터 딕셔너리 생성
                    params = dict(zip(param_names, param_combo))
                    
                    # 전략 인스턴스 생성 (파라미터 적용)
                    strategy_class = self.strategies[strategy_name]
                    
                    # 백테스팅에서는 supabase_client 없이 전략 생성
                    try:
                        # supabase_client 없이 초기화 시도
                        strategy = strategy_class(**params)
                    except TypeError:
                        # supabase_client가 필요한 경우 전달
                        strategy = strategy_class(self.supabase_client, **params)
                    
                    # 백테스트 실행
                    backtester = Backtester(initial_capital=initial_capital)
                    result = backtester.run_backtest(strategy, market_data, symbol)
                    
                    # 결과 저장
                    optimization_results.append({
                        'parameters': params,
                        'result': result,
                        'return_pct': result.total_return_pct,
                        'sharpe_ratio': result.sharpe_ratio,
                        'max_drawdown': result.max_drawdown_pct
                    })
                    
                except Exception as e:
                    logger.warning(f"파라미터 조합 {params} 테스트 실패: {e}")
                    continue
            
            # 결과 정렬 (수익률 기준 내림차순)
            optimization_results.sort(key=lambda x: x['return_pct'], reverse=True)
            
            # 최적화 결과 출력
            self._print_optimization_summary(optimization_results[:10])  # 상위 10개만
            
            logger.info("파라미터 최적화 완료")
            return optimization_results
            
        except Exception as e:
            logger.error(f"파라미터 최적화 실패: {e}")
            raise
    
    def _print_result_summary(self, result: 'BacktestResult'):
        """백테스트 결과 요약 출력"""
        print("\n" + "="*60)
        print(f"📊 백테스트 결과: {result.strategy_name}")
        print("="*60)
        print(f"심볼: {result.symbol}")
        print(f"기간: {result.start_date.strftime('%Y-%m-%d')} ~ {result.end_date.strftime('%Y-%m-%d')}")
        print(f"총 수익률: {result.total_return_pct:.2f}%")
        print(f"총 거래: {result.total_trades}회")
        print(f"승률: {result.win_rate:.1f}%")
        print(f"최대 낙폭: {result.max_drawdown_pct:.2f}%")
        print(f"샤프 비율: {result.sharpe_ratio:.3f}")
        print("="*60)
    
    def _print_comparison_summary(self, results: list):
        """비교 결과 요약 출력"""
        print("\n" + "="*80)
        print("⚖️ 전략 비교 결과")
        print("="*80)
        
        # 수익률 기준 정렬
        sorted_results = sorted(results, key=lambda x: x.total_return_pct, reverse=True)
        
        print(f"{'순위':<4} {'전략':<20} {'수익률':<10} {'거래수':<8} {'승률':<8} {'최대낙폭':<10} {'샤프비율':<10}")
        print("-"*80)
        
        for i, result in enumerate(sorted_results, 1):
            rank_icon = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}위"
            print(f"{rank_icon:<4} {result.strategy_name:<20} {result.total_return_pct:>8.2f}% "
                  f"{result.total_trades:>6}회 {result.win_rate:>6.1f}% {result.max_drawdown_pct:>8.2f}% "
                  f"{result.sharpe_ratio:>8.3f}")
        
        print("="*80)
    
    def _print_optimization_summary(self, results: list):
        """최적화 결과 요약 출력"""
        print("\n" + "="*100)
        print("🔧 파라미터 최적화 결과 (상위 10개)")
        print("="*100)
        
        for i, opt_result in enumerate(results, 1):
            params = opt_result['parameters']
            result = opt_result['result']
            
            print(f"\n{i}위: 수익률 {result.total_return_pct:.2f}%")
            print(f"  파라미터: {params}")
            print(f"  샤프비율: {result.sharpe_ratio:.3f}, 최대낙폭: {result.max_drawdown_pct:.2f}%")
        
        print("="*100)
    
    def _save_result_to_file(self, result: 'BacktestResult'):
        """결과를 파일로 저장"""
        try:
            # 결과 디렉토리 생성
            results_dir = project_root / 'backtest_results'
            results_dir.mkdir(exist_ok=True)
            
            # 파일명 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{result.strategy_name}_{result.symbol}_{timestamp}.txt"
            filepath = results_dir / filename
            
            # 분석 수행
            analyzer = PerformanceAnalyzer()
            analysis = analyzer.analyze_performance(result)
            
            # 리포터로 저장
            reporter = BacktestReporter()
            success = reporter.save_detailed_report(result, analysis, str(filepath))
            
            if success:
                logger.info(f"결과 파일 저장: {filepath}")
            else:
                logger.error("결과 파일 저장 실패")
            
            # 차트 이미지들을 로컬에 저장
            self._save_charts_to_local(result, analysis, timestamp)
                
        except Exception as e:
            logger.error(f"결과 파일 저장 중 에러: {e}")
    
    def _save_charts_to_local(self, result: 'BacktestResult', analysis: dict, timestamp: str):
        """차트들을 로컬 파일로 저장"""
        try:
            charts = analysis.get('charts', {})
            if not charts:
                logger.info("저장할 차트가 없습니다")
                return
            
            # 차트 디렉토리 생성
            charts_dir = project_root / 'backtest_results' / 'charts'
            charts_dir.mkdir(exist_ok=True)
            
            import base64
            
            # 각 차트 저장
            for chart_name, chart_base64 in charts.items():
                if chart_base64:
                    try:
                        # Base64 디코딩
                        image_data = base64.b64decode(chart_base64)
                        
                        # 파일명 생성
                        chart_filename = f"{result.strategy_name}_{result.symbol}_{chart_name}_{timestamp}.png"
                        chart_filepath = charts_dir / chart_filename
                        
                        # 파일 저장
                        with open(chart_filepath, 'wb') as f:
                            f.write(image_data)
                        
                        logger.info(f"차트 저장: {chart_filepath}")
                        
                    except Exception as e:
                        logger.error(f"차트 저장 실패 ({chart_name}): {e}")
            
        except Exception as e:
            logger.error(f"차트 로컬 저장 중 에러: {e}")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='암호화폐 전략 백테스팅')
    parser.add_argument('--strategy', '-s', default='MACD_ATR',
                       help='전략 이름 (기본: MACD_ATR)')
    parser.add_argument('--symbol', default='BTCUSDT',
                       help='거래 심볼 (기본: BTCUSDT)')
    parser.add_argument('--days', '-d', type=int, default=30,
                       help='백테스트 기간 일수 (기본: 30)')
    parser.add_argument('--capital', '-c', type=float, default=10000.0,
                       help='초기 자본 (기본: 10000)')
    parser.add_argument('--compare', nargs='+',
                       help='여러 전략 비교 (예: --compare MACD_ATR RSI_BB)')
    parser.add_argument('--optimize', action='store_true',
                       help='파라미터 최적화 실행')
    parser.add_argument('--no-slack', action='store_true',
                       help='Slack 전송 비활성화')
    parser.add_argument('--recommend-symbols', action='store_true',
                       help='변동성/거래량 기반 심볼 #!/usr/bin/env python3')
    
    args = parser.parse_args()
    
    try:
        print("🚀 백테스팅 시스템 시작")
        print("="*50)
        
        # 백테스트 실행기 초기화
        runner = BacktestRunner()
        if not runner.initialize():
            print("❌ 초기화 실패")
            sys.exit(1)
        
        send_to_slack = not args.no_slack
        
        # 실행 모드 결정
        if args.compare:
            # 여러 전략 비교
            print(f"⚖️ 전략 비교 모드: {args.compare}")
            runner.run_strategy_comparison(
                strategies=args.compare,
                symbol=args.symbol,
                days=args.days,
                initial_capital=args.capital,
                send_to_slack=send_to_slack
            )
            
        elif args.optimize:
            # 파라미터 최적화
            print(f"🔧 파라미터 최적화 모드: {args.strategy}")
            
            # MACD_ATR 전략의 기본 최적화 범위
            if args.strategy == 'MACD_ATR':
                parameter_ranges = {
                    'macd_fast': [8, 12, 16],
                    'macd_slow': [20, 26, 32],
                    'macd_signal': [6, 9, 12],
                    'atr_period': [10, 14, 18],
                    'atr_multiplier': [2.0, 2.5, 3.0, 3.5]
                }
            else:
                print(f"❌ {args.strategy} 전략의 최적화 파라미터가 정의되지 않았습니다")
                sys.exit(1)
            
            runner.run_parameter_optimization(
                strategy_name=args.strategy,
                parameter_ranges=parameter_ranges,
                symbol=args.symbol,
                days=args.days,
                initial_capital=args.capital
            )
            
        else:
            # 단일 전략 백테스트
            print(f"📊 단일 전략 모드: {args.strategy}")
            runner.run_single_backtest(
                strategy_name=args.strategy,
                symbol=args.symbol,
                days=args.days,
                initial_capital=args.capital,
                send_to_slack=send_to_slack
            )
        
        print("\n✅ 백테스팅 완료!")
        
    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n❌ 백테스팅 실행 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    """
    백테스팅 실행 예시:
    
    # 기본 백테스트 (MACD_ATR, 30일)
    python run_backtest.py
    
    # 특정 전략과 기간
    python run_backtest.py --strategy MACD_ATR --days 60 --capital 50000
    
    # 여러 전략 비교
    python run_backtest.py --compare MACD_ATR RSI_BB --days 30
    
    # 파라미터 최적화
    python run_backtest.py --strategy MACD_ATR --optimize --days 60
    
    # Slack 전송 없이 실행
    python run_backtest.py --no-slack
    """
    main()