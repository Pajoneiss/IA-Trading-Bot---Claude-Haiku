"""
Phase 4 - Performance Analyzer
Análise completa de performance de trading
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """
    Performance Analyzer - Análise de métricas de trading
    
    Calcula:
    - PnL (diário, semanal, mensal)
    - Win Rate
    - RR médio
    - Profit Factor
    - Drawdown máximo
    - Best/Worst por símbolo e estratégia
    - Tempo médio em trade
    - Taxa de rejeição do Quality Gate
    """
    
    def __init__(self, log_file: str = "data/trade_log.jsonl"):
        """
        Inicializa Performance Analyzer
        
        Args:
            log_file: Caminho do arquivo JSONL de trades
        """
        self.log_file = Path(log_file)
        logger.info("[PERFORMANCE ANALYZER] Inicializado")
    
    def get_summary(self, period: str = "daily") -> Dict[str, Any]:
        """
        Retorna sumário de performance
        
        Args:
            period: 'daily', 'weekly', 'monthly'
            
        Returns:
            Dict com todas as métricas calculadas
        """
        try:
            # Define período
            now = datetime.now(timezone.utc)
            
            if period == "daily":
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "weekly":
                start_time = now - timedelta(days=7)
            elif period == "monthly":
                start_time = now - timedelta(days=30)
            else:
                start_time = now - timedelta(days=1)
            
            # Carrega eventos do período
            events = self._load_events_since(start_time)
            
            if not events:
                return self._empty_summary(period)
            
            # Separa por tipo
            closes = [e for e in events if e.get('type') == 'close']
            partials = [e for e in events if e.get('type') == 'partial']
            rejections = [e for e in events if e.get('type') == 'rejection']
            skips = [e for e in events if e.get('type') == 'skip']
            
            # Calcula métricas
            pnl_metrics = self._calculate_pnl(closes, partials)
            win_rate = self._calculate_win_rate(closes)
            rr_avg = self._calculate_avg_rr(closes)
            profit_factor = self._calculate_profit_factor(closes)
            best_worst = self._calculate_best_worst(closes)
            avg_duration = self._calculate_avg_duration(closes)
            rejection_rate = self._calculate_rejection_rate(closes, rejections, skips)
            
            # Monta sumário
            summary = {
                'period': period,
                'start_date': start_time.isoformat(),
                'end_date': now.isoformat(),
                'total_trades': len(closes),
                'total_partials': len(partials),
                'total_rejections': len(rejections),
                'total_skips': len(skips),
                'pnl': pnl_metrics,
                'win_rate': win_rate,
                'avg_rr': rr_avg,
                'profit_factor': profit_factor,
                'best_worst': best_worst,
                'avg_duration': avg_duration,
                'rejection_rate': rejection_rate
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao gerar sumário: {e}", exc_info=True)
            return self._empty_summary(period)
    
    def _load_events_since(self, start_time: datetime) -> List[Dict[str, Any]]:
        """
        Carrega eventos desde start_time
        
        Args:
            start_time: Data/hora de início
            
        Returns:
            Lista de eventos
        """
        events = []
        
        try:
            if not self.log_file.exists():
                return events
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        
                        # Parse timestamp
                        event_time = datetime.fromisoformat(event.get('timestamp', ''))
                        
                        # Filtra por período
                        if event_time >= start_time:
                            events.append(event)
                            
                    except json.JSONDecodeError:
                        continue
                    except (ValueError, TypeError):
                        continue
            
            logger.debug(f"[PERFORMANCE ANALYZER] Carregados {len(events)} eventos")
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao carregar eventos: {e}")
        
        return events
    
    def _calculate_pnl(self, closes: List[Dict], partials: List[Dict]) -> Dict[str, Any]:
        """Calcula PnL total, médio, etc"""
        try:
            # PnL de closes
            close_pnls = [c.get('pnl_value', 0) for c in closes]
            
            # PnL de partials
            partial_pnls = [p.get('pnl_value', 0) for p in partials]
            
            # Total
            total_pnl = sum(close_pnls) + sum(partial_pnls)
            avg_pnl = total_pnl / max(len(closes), 1)
            
            # Winners vs losers
            winners = [p for p in close_pnls if p > 0]
            losers = [p for p in close_pnls if p < 0]
            
            return {
                'total': round(total_pnl, 2),
                'avg': round(avg_pnl, 2),
                'total_closes': round(sum(close_pnls), 2),
                'total_partials': round(sum(partial_pnls), 2),
                'winners': len(winners),
                'losers': len(losers),
                'avg_win': round(sum(winners) / len(winners), 2) if winners else 0,
                'avg_loss': round(sum(losers) / len(losers), 2) if losers else 0
            }
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular PnL: {e}")
            return {'total': 0, 'avg': 0}
    
    def _calculate_win_rate(self, closes: List[Dict]) -> float:
        """Calcula win rate"""
        try:
            if not closes:
                return 0.0
            
            winners = sum(1 for c in closes if c.get('pnl_value', 0) > 0)
            win_rate = (winners / len(closes)) * 100
            
            return round(win_rate, 2)
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular win rate: {e}")
            return 0.0
    
    def _calculate_avg_rr(self, closes: List[Dict]) -> float:
        """Calcula R-múltiplo médio"""
        try:
            rrs = [c.get('rr') for c in closes if c.get('rr') is not None]
            
            if not rrs:
                return 0.0
            
            return round(sum(rrs) / len(rrs), 2)
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular avg RR: {e}")
            return 0.0
    
    def _calculate_profit_factor(self, closes: List[Dict]) -> float:
        """Calcula Profit Factor"""
        try:
            gross_profit = sum(c.get('pnl_value', 0) for c in closes if c.get('pnl_value', 0) > 0)
            gross_loss = abs(sum(c.get('pnl_value', 0) for c in closes if c.get('pnl_value', 0) < 0))
            
            if gross_loss == 0:
                return 0.0 if gross_profit == 0 else 999.0
            
            return round(gross_profit / gross_loss, 2)
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular profit factor: {e}")
            return 0.0
    
    def _calculate_best_worst(self, closes: List[Dict]) -> Dict[str, Any]:
        """Calcula best/worst por símbolo e estratégia"""
        try:
            if not closes:
                return {}
            
            # Por símbolo
            by_symbol = defaultdict(list)
            for c in closes:
                symbol = c.get('symbol', 'UNKNOWN')
                pnl = c.get('pnl_value', 0)
                by_symbol[symbol].append(pnl)
            
            symbol_totals = {s: sum(pnls) for s, pnls in by_symbol.items()}
            
            best_symbol = max(symbol_totals, key=symbol_totals.get) if symbol_totals else 'N/A'
            worst_symbol = min(symbol_totals, key=symbol_totals.get) if symbol_totals else 'N/A'
            
            # Por estratégia
            by_strategy = defaultdict(list)
            for c in closes:
                strategy = c.get('strategy', 'UNKNOWN')
                pnl = c.get('pnl_value', 0)
                by_strategy[strategy].append(pnl)
            
            strategy_totals = {s: sum(pnls) for s, pnls in by_strategy.items()}
            
            best_strategy = max(strategy_totals, key=strategy_totals.get) if strategy_totals else 'N/A'
            worst_strategy = min(strategy_totals, key=strategy_totals.get) if strategy_totals else 'N/A'
            
            # Melhor/pior trade
            best_trade = max(closes, key=lambda c: c.get('pnl_value', 0))
            worst_trade = min(closes, key=lambda c: c.get('pnl_value', 0))
            
            return {
                'best_symbol': {
                    'symbol': best_symbol,
                    'pnl': round(symbol_totals.get(best_symbol, 0), 2)
                },
                'worst_symbol': {
                    'symbol': worst_symbol,
                    'pnl': round(symbol_totals.get(worst_symbol, 0), 2)
                },
                'best_strategy': {
                    'strategy': best_strategy,
                    'pnl': round(strategy_totals.get(best_strategy, 0), 2)
                },
                'worst_strategy': {
                    'strategy': worst_strategy,
                    'pnl': round(strategy_totals.get(worst_strategy, 0), 2)
                },
                'best_trade': {
                    'symbol': best_trade.get('symbol'),
                    'pnl': round(best_trade.get('pnl_value', 0), 2),
                    'pnl_pct': round(best_trade.get('pnl_percent', 0), 2)
                },
                'worst_trade': {
                    'symbol': worst_trade.get('symbol'),
                    'pnl': round(worst_trade.get('pnl_value', 0), 2),
                    'pnl_pct': round(worst_trade.get('pnl_percent', 0), 2)
                }
            }
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular best/worst: {e}")
            return {}
    
    def _calculate_avg_duration(self, closes: List[Dict]) -> str:
        """Calcula duração média dos trades"""
        try:
            durations = [c.get('duration_seconds', 0) for c in closes if c.get('duration_seconds')]
            
            if not durations:
                return "N/A"
            
            avg_seconds = sum(durations) / len(durations)
            
            hours = int(avg_seconds // 3600)
            minutes = int((avg_seconds % 3600) // 60)
            
            return f"{hours}h {minutes}m"
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular avg duration: {e}")
            return "N/A"
    
    def _calculate_rejection_rate(self, closes: List[Dict], rejections: List[Dict], skips: List[Dict]) -> Dict[str, Any]:
        """Calcula taxa de rejeição"""
        try:
            total_signals = len(closes) + len(rejections) + len(skips)
            
            if total_signals == 0:
                return {
                    'total_signals': 0,
                    'executed': 0,
                    'rejected': 0,
                    'skipped': 0,
                    'rejection_rate': 0.0,
                    'skip_rate': 0.0
                }
            
            rejection_rate = (len(rejections) / total_signals) * 100
            skip_rate = (len(skips) / total_signals) * 100
            
            return {
                'total_signals': total_signals,
                'executed': len(closes),
                'rejected': len(rejections),
                'skipped': len(skips),
                'rejection_rate': round(rejection_rate, 2),
                'skip_rate': round(skip_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"[PERFORMANCE ANALYZER] Erro ao calcular rejection rate: {e}")
            return {'rejection_rate': 0.0, 'skip_rate': 0.0}
    
    def _empty_summary(self, period: str) -> Dict[str, Any]:
        """Retorna sumário vazio"""
        return {
            'period': period,
            'total_trades': 0,
            'pnl': {'total': 0, 'avg': 0},
            'win_rate': 0.0,
            'avg_rr': 0.0,
            'profit_factor': 0.0,
            'best_worst': {},
            'avg_duration': "N/A",
            'rejection_rate': {'rejection_rate': 0.0, 'skip_rate': 0.0}
        }
