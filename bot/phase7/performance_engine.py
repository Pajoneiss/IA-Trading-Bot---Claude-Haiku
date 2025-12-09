"""
Phase 7 - Performance Engine
Análise de métricas por símbolo/estratégia/estilo
"""
import logging
from collections import defaultdict
from typing import Dict, Any, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PerformanceEngine:
    """Analisador de performance de estratégias"""
    
    def __init__(self, journal, logger_instance=None):
        self.journal = journal
        self.logger = logger_instance or logger
    
    def get_symbol_stats(self, symbol: str = None) -> Dict[str, Any]:
        """Estatísticas por símbolo"""
        trades = self.journal.get_all_trades()
        
        if not trades:
            return {'error': 'Sem trades'}
        
        stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'total_pnl': 0.0, 'pnls': []})
        
        for t in trades:
            sym = t.get('symbol', 'UNKNOWN')
            if symbol and sym != symbol:
                continue
            
            stats[sym]['count'] += 1
            pnl = t.get('pnl_pct', 0)
            stats[sym]['pnls'].append(pnl)
            stats[sym]['total_pnl'] += pnl
            if pnl > 0:
                stats[sym]['wins'] += 1
        
        result = {}
        for sym, data in stats.items():
            if data['count'] > 0:
                result[sym] = {
                    'trades': data['count'],
                    'win_rate': (data['wins'] / data['count']) * 100,
                    'avg_pnl': data['total_pnl'] / data['count'],
                    'expectancy': data['total_pnl'] / data['count']
                }
        
        return result if not symbol else result.get(symbol, {'error': 'Sem dados'})
    
    def get_best_worst_pairs(self, limit: int = 3) -> Dict[str, List]:
        """Top e piores pares"""
        stats = self.get_symbol_stats()
        
        if 'error' in stats:
            return {'best': [], 'worst': []}
        
        sorted_by_exp = sorted(stats.items(), key=lambda x: x[1]['expectancy'], reverse=True)
        
        return {
            'best': sorted_by_exp[:limit],
            'worst': sorted_by_exp[-limit:]
        }
    
    def get_weekly_summary(self) -> Dict[str, Any]:
        """Resumo da última semana"""
        trades = self.journal.get_all_trades()
        
        if not trades:
            return {'error': 'Sem trades'}
        
        # Filtra última semana
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent = []
        
        for t in trades:
            try:
                ts = t.get('timestamp_close', '')
                if ts:
                    trade_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    if trade_time >= week_ago:
                        recent.append(t)
            except:
                continue
        
        if not recent:
            return {'error': 'Sem trades na semana'}
        
        wins = sum(1 for t in recent if t.get('pnl_pct', 0) > 0)
        total_pnl = sum(t.get('pnl_pct', 0) for t in recent)
        
        return {
            'trades': len(recent),
            'win_rate': (wins / len(recent)) * 100,
            'avg_pnl': total_pnl / len(recent),
            'best_trade': max(recent, key=lambda x: x.get('pnl_pct', 0)),
            'worst_trade': min(recent, key=lambda x: x.get('pnl_pct', 0))
        }
    
    def get_real_vs_paper_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Compara performance REAL vs PAPER
        
        Args:
            days: Período em dias
            
        Returns:
            Dict com comparação
        """
        trades = self.journal.get_all_trades()
        
        if not trades:
            return {'error': 'Sem trades'}
        
        # Filtra período
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent = []
        
        for t in trades:
            try:
                ts = t.get('timestamp_close', '')
                if ts:
                    trade_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    if trade_time >= cutoff:
                        recent.append(t)
            except:
                continue
        
        # Separa REAL vs PAPER
        real_trades = [t for t in recent if not t.get('is_paper', False)]
        paper_trades = [t for t in recent if t.get('is_paper', False)]
        
        def calc_stats(trades_list):
            if not trades_list:
                return None
            
            wins = sum(1 for t in trades_list if t.get('pnl_pct', 0) > 0)
            total_pnl = sum(t.get('pnl_pct', 0) for t in trades_list)
            
            return {
                'trades': len(trades_list),
                'win_rate': (wins / len(trades_list)) * 100,
                'avg_pnl': total_pnl / len(trades_list),
                'expectancy': total_pnl / len(trades_list)
            }
        
        return {
            'period_days': days,
            'real': calc_stats(real_trades),
            'paper': calc_stats(paper_trades)
        }
    
    def get_shadow_experiment_stats(self, shadow_label: str) -> Dict[str, Any]:
        """
        Estatísticas de um experimento shadow específico
        
        Args:
            shadow_label: Label do experimento (ex: "SHADOW:aggressive_swing")
            
        Returns:
            Dict com estatísticas
        """
        trades = self.journal.get_all_trades()
        
        # Filtra por shadow label
        shadow_trades = [
            t for t in trades 
            if t.get('is_paper', False) and t.get('paper_profile') == shadow_label
        ]
        
        if not shadow_trades:
            return {'error': 'Sem trades para este experimento'}
        
        wins = sum(1 for t in shadow_trades if t.get('pnl_pct', 0) > 0)
        total_pnl = sum(t.get('pnl_pct', 0) for t in shadow_trades)
        
        return {
            'experiment': shadow_label,
            'trades': len(shadow_trades),
            'win_rate': (wins / len(shadow_trades)) * 100,
            'avg_pnl': total_pnl / len(shadow_trades),
            'expectancy': total_pnl / len(shadow_trades),
            'total_pnl_pct': total_pnl
        }
