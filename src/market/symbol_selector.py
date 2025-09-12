#!/usr/bin/env python3
"""
심볼 선택기 - 사용자 인터페이스
파일 위치: src/market/symbol_selector.py
"""

import sys
from typing import List, Optional
from pathlib import Path

# 프로젝트 루트 경로 설정
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.market.market_analyzer import MarketAnalyzer, MarketFilter, SymbolMetrics
from src.utils.logger import get_logger

logger = get_logger(__name__)

class SymbolSelector:
    """심볼 선택 사용자 인터페이스"""
    
    def __init__(self, binance_client):
        """
        심볼 선택기 초기화
        
        Args:
            binance_client: BinanceClient 인스턴스
        """
        self.analyzer = MarketAnalyzer(binance_client)
        
        logger.info("SymbolSelector 초기화 완료")
    
    def interactive_symbol_selection(self) -> List[str]:
        """대화형 심볼 선택"""
        try:
            print("\n" + "="*60)
            print("📊 암호화폐 심볼 추천 시스템")
            print("="*60)
            
            # 1. 사용자 선호도 입력
            preferences = self._get_user_preferences()
            
            # 2. 시장 분석 실행
            print("\n🔍 시장 분석 중...")
            symbol_metrics = self.analyzer.analyze_market(preferences)
            
            if not symbol_metrics:
                print("❌ 조건에 맞는 심볼이 없습니다.")
                return []
            
            # 3. 추천 결과 표시
            self._display_recommendations(symbol_metrics, preferences)
            
            # 4. 사용자 선택
            selected_symbols = self._get_user_selection(symbol_metrics)
            
            return selected_symbols
            
        except KeyboardInterrupt:
            print("\n⏹️ 사용자에 의해 중단됨")
            return []
        except Exception as e:
            logger.error(f"대화형 선택 실패: {e}")
            print(f"❌ 에러 발생: {e}")
            return []
    
    def _get_user_preferences(self) -> MarketFilter:
        """사용자 선호도 입력"""
        try:
            print("\n📋 트레이딩 선호도를 설정해주세요:")
            
            # 트레이딩 스타일 선택
            print("\n1. 트레이딩 스타일:")
            print("   1) 안정적 (낮은 변동성, 높은 거래량)")
            print("   2) 균형적 (중간 변동성, 적당한 거래량) - 기본값")
            print("   3) 공격적 (높은 변동성, 높은 수익 잠재력)")
            
            style_choice = input("스타일 선택 (1-3, 엔터=기본값): ").strip()
            
            # 거래량 기준
            print("\n2. 최소 일일 거래량:")
            print("   1) 1천만 USDT (소형)")
            print("   2) 5천만 USDT (중형) - 기본값")
            print("   3) 1억 USDT (대형)")
            
            volume_choice = input("거래량 선택 (1-3, 엔터=기본값): ").strip()
            
            # 추천 개수
            try:
                top_n = int(input("\n3. 추천받을 심볼 개수 (기본값: 10): ").strip() or "10")
                top_n = max(5, min(top_n, 50))  # 5-50개 제한
            except ValueError:
                top_n = 10
            
            # 설정 적용
            if style_choice == "1":  # 안정적
                market_filter = MarketFilter(
                    min_volatility=1.0,
                    max_volatility=8.0,
                    min_volume_usdt=self._get_volume_threshold(volume_choice),
                    top_n=top_n
                )
            elif style_choice == "3":  # 공격적
                market_filter = MarketFilter(
                    min_volatility=5.0,
                    max_volatility=25.0,
                    min_volume_usdt=self._get_volume_threshold(volume_choice),
                    top_n=top_n
                )
            else:  # 균형적 (기본값)
                market_filter = MarketFilter(
                    min_volatility=2.0,
                    max_volatility=15.0,
                    min_volume_usdt=self._get_volume_threshold(volume_choice),
                    top_n=top_n
                )
            
            return market_filter
            
        except Exception as e:
            logger.warning(f"사용자 선호도 입력 실패, 기본값 사용: {e}")
            return MarketFilter()
    
    def _get_volume_threshold(self, volume_choice: str) -> float:
        """거래량 임계값 반환"""
        volume_map = {
            "1": 10_000_000,    # 1천만
            "3": 100_000_000,   # 1억
        }
        return volume_map.get(volume_choice, 50_000_000)  # 기본값: 5천만
    
    def _display_recommendations(self, symbol_metrics: List[SymbolMetrics], 
                               market_filter: MarketFilter):
        """추천 결과 표시"""
        try:
            print(f"\n📈 추천 결과 (상위 {len(symbol_metrics)}개)")
            print("-" * 80)
            print(f"{'순위':<4} {'심볼':<12} {'가격':<12} {'24h 변화':<10} {'거래량(M USDT)':<15} {'점수':<8}")
            print("-" * 80)
            
            for metrics in symbol_metrics:
                volume_m = metrics.volume_24h_usdt / 1_000_000
                change_str = f"{metrics.price_change_pct_24h:+.2f}%"
                
                print(f"{metrics.rank:<4} {metrics.symbol:<12} "
                      f"${metrics.price:<11.4f} {change_str:<10} "
                      f"{volume_m:<15.1f} {metrics.total_score:<8.1f}")
            
            print("-" * 80)
            
            # 요약 통계
            avg_volatility = sum(abs(m.price_change_pct_24h) for m in symbol_metrics) / len(symbol_metrics)
            avg_volume = sum(m.volume_24h_usdt for m in symbol_metrics) / len(symbol_metrics) / 1_000_000
            
            print(f"\n📊 요약:")
            print(f"   평균 변동성: {avg_volatility:.2f}%")
            print(f"   평균 거래량: {avg_volume:.1f}M USDT")
            print(f"   필터 조건: 변동성 {market_filter.min_volatility}-{market_filter.max_volatility}%, "
                  f"거래량 {market_filter.min_volume_usdt/1_000_000:.0f}M+ USDT")
            
        except Exception as e:
            logger.error(f"추천 결과 표시 실패: {e}")
    
    def _get_user_selection(self, symbol_metrics: List[SymbolMetrics]) -> List[str]:
        """사용자 선택 입력"""
        try:
            print(f"\n🎯 심볼 선택:")
            print("   - 개별 선택: 순위 번호 입력 (예: 1,3,5)")
            print("   - 범위 선택: 범위 입력 (예: 1-5)")
            print("   - 상위 N개: 숫자만 입력 (예: 3)")
            print("   - 전체 선택: all")
            print("   - 취소: 엔터")
            
            selection = input("\n선택: ").strip().lower()
            
            if not selection:
                return []
            
            if selection == "all":
                return [m.symbol for m in symbol_metrics]
            
            # 숫자만 입력한 경우 (상위 N개)
            if selection.isdigit():
                n = min(int(selection), len(symbol_metrics))
                return [symbol_metrics[i].symbol for i in range(n)]
            
            # 범위 선택 (1-5)
            if "-" in selection:
                try:
                    start, end = map(int, selection.split("-", 1))
                    start = max(1, start) - 1  # 0-based index
                    end = min(end, len(symbol_metrics))
                    return [symbol_metrics[i].symbol for i in range(start, end)]
                except ValueError:
                    print("❌ 잘못된 범위 형식입니다.")
                    return []
            
            # 개별 선택 (1,3,5)
            if "," in selection:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    valid_indices = [i for i in indices if 0 <= i < len(symbol_metrics)]
                    return [symbol_metrics[i].symbol for i in valid_indices]
                except ValueError:
                    print("❌ 잘못된 선택 형식입니다.")
                    return []
            
            print("❌ 올바른 형식으로 입력해주세요.")
            return []
            
        except Exception as e:
            logger.error(f"사용자 선택 입력 실패: {e}")
            return []
    
    def quick_recommend(self, strategy_type: str = "trend_following", 
                       top_n: int = 5) -> List[str]:
        """빠른 추천 (비대화형)"""
        try:
            logger.info(f"빠른 추천: {strategy_type} 전략용 상위 {top_n}개")
            
            return self.analyzer.recommend_for_strategy(strategy_type)[:top_n]
            
        except Exception as e:
            logger.error(f"빠른 추천 실패: {e}")
            return []
    
    def analyze_specific_symbols(self, symbols: List[str]) -> List[SymbolMetrics]:
        """특정 심볼들 분석"""
        try:
            logger.info(f"특정 심볼 분석: {symbols}")
            
            results = []
            for symbol in symbols:
                metrics = self.analyzer.get_symbol_analysis(symbol)
                if metrics:
                    results.append(metrics)
            
            # 점수 기준 정렬
            results.sort(key=lambda x: x.total_score, reverse=True)
            
            # 랭킹 재부여
            for i, metrics in enumerate(results, 1):
                metrics.rank = i
            
            return results
            
        except Exception as e:
            logger.error(f"특정 심볼 분석 실패: {e}")
            return []


def main():
    """메인 함수 - 독립 실행용"""
    try:
        from src.api.binance_client import BinanceClient
        from dotenv import load_dotenv
        
        # 환경변수 로드
        env_path = project_root / 'config' / '.env'
        if env_path.exists():
            load_dotenv(env_path)
        
        # Binance 클라이언트 초기화
        import os
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            print("❌ Binance API 키가 설정되지 않았습니다.")
            return
        
        binance_client = BinanceClient(api_key, api_secret)
        
        # 심볼 선택기 실행
        selector = SymbolSelector(binance_client)
        selected_symbols = selector.interactive_symbol_selection()
        
        if selected_symbols:
            print(f"\n✅ 선택된 심볼: {', '.join(selected_symbols)}")
            print("\n이 심볼들로 백테스트를 실행하시겠습니까?")
            
            if input("백테스트 실행? (y/N): ").strip().lower() == 'y':
                print("백테스트 실행 명령:")
                for symbol in selected_symbols:
                    print(f"python run_backtest.py --symbol {symbol} --days 60")
        else:
            print("선택된 심볼이 없습니다.")
        
    except Exception as e:
        print(f"❌ 실행 실패: {e}")


if __name__ == "__main__":
    main()