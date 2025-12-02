"""
PnL Tracker - Análise detalhada de Performance
Rastreia PnL diário, semanal, mensal com win rate e melhores/piores trades
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class PnLTracker:
    """
    Rastreia e analisa performance do bot
    """
    
    def __init__(self, main_bot):
        self.main_bot = main_bot
        self.trade_history = []  # Lista de trades fechados
        
    def analyze_pnl(self) -> Dict:
        """
        Analisa PnL em todas as períodos
        
        Returns:
            {
                'daily': {...},
                'weekly': {...},
                'monthly': {...}
            }
        """
        now = datetime.utcnow()
        
        return {
            'daily': self._analyze_period(now - timedelta(days=1), now, 'Diário'),
            'weekly': self._analyze_period(now - timedelta(days=7), now, 'Semanal'),
            'monthly': self._analyze_period(now - timedelta(days=30), now, 'Mensal')
        }
    
    def _analyze_period(self, start: datetime, end: datetime, period_name: str) -> Dict:
        """
        Analisa performance em um período específico
        """
        try:
            # Busca trades do período
            trades = self._get_trades_in_period(start, end)
            
            if not trades:
                return {
                    'period': period_name,
                    'realized_pnl': 0.0,
                    'unrealized_pnl': 0.0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'best_trades': [],
                    'worst_trades': []
                }
            
            # Calcula métricas
            realized_pnl = sum(t['pnl'] for t in trades if t['closed'])
            winning_trades = [t for t in trades if t['closed'] and t['pnl'] > 0]
            losing_trades = [t for t in trades if t['closed'] and t['pnl'] < 0]
            
            win_rate = (len(winning_trades) / len([t for t in trades if t['closed']]) * 100) if trades else 0
            
            # Melhores e piores trades
            closed_trades = [t for t in trades if t['closed']]
            best_trades = sorted(closed_trades, key=lambda x: x['pnl'], reverse=True)[:3]
            worst_trades = sorted(closed_trades, key=lambda x: x['pnl'])[:3]
            
            # PnL não-realizado (posições abertas)
            open_positions = self._get_open_positions_pnl()
            unrealized_pnl = open_positions['total_pnl']
            
            return {
                'period': period_name,
                'realized_pnl': realized_pnl,
                'unrealized_pnl': unrealized_pnl,
                'total_pnl': realized_pnl + unrealized_pnl,
                'win_rate': win_rate,
                'total_trades': len([t for t in trades if t['closed']]),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'best_trades': best_trades,
                'worst_trades': worst_trades
            }
            
        except Exception as e:
            logger.error(f"[PNL_TRACKER] Erro ao analisar período {period_name}: {e}")
            return self._get_empty_analysis(period_name)
    
    def _get_trades_in_period(self, start: datetime, end: datetime) -> List[Dict]:
        """
        Busca trades no período
        
        TODO: Implementar baseado no histórico real do bot
        Por enquanto, retorna mock data
        """
        # Aqui você deve buscar do histórico real
        # Por exemplo, de um banco de dados ou arquivo de log
        
        # Mock data para demonstração
        return []
    
    def _get_open_positions_pnl(self) -> Dict:
        """
        Calcula PnL de posições abertas
        """
        try:
            # Busca preços atuais
            try:
                prices = self.main_bot.client.get_all_mids()
            except:
                prices = {}
            
            positions = self.main_bot.position_manager.get_all_positions(current_prices=prices)
            
            total_pnl = 0.0
            for pos in positions:
                pnl = pos.get('unrealized_pnl', 0.0)
                total_pnl += pnl
            
            return {
                'count': len(positions),
                'total_pnl': total_pnl
            }
            
        except Exception as e:
            logger.error(f"[PNL_TRACKER] Erro ao calcular PnL aberto: {e}")
            return {'count': 0, 'total_pnl': 0.0}
    
    def _get_empty_analysis(self, period_name: str) -> Dict:
        """Retorna análise vazia"""
        return {
            'period': period_name,
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'total_pnl': 0.0,
            'win_rate': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'best_trades': [],
            'worst_trades': []
        }
    
    def format_for_telegram(self, analysis: Dict) -> str:
        """
        Formata análise completa para Telegram
        """
        msg = "📉 *PNL — Análise Completa*\n\n"
        
        # Diário
        daily = analysis['daily']
        msg += f"📊 *{daily['period'].upper()}*\n"
        msg += self._format_period(daily) + "\n"
        
        # Semanal
        weekly = analysis['weekly']
        msg += f"📅 *{weekly['period'].upper()} (Últimos 7 dias)*\n"
        msg += self._format_period(weekly) + "\n"
        
        # Mensal
        monthly = analysis['monthly']
        msg += f"📆 *{monthly['period'].upper()} (Últimos 30 dias)*\n"
        msg += self._format_period(monthly) + "\n"
        
        # Melhores trades (do mês)
        if monthly['best_trades']:
            msg += "🔥 *MELHORES TRADES (30d)*\n"
            for i, trade in enumerate(monthly['best_trades'], 1):
                msg += f"   {i}. {trade['coin']}: *${trade['pnl']:+.2f}* ({trade['pnl_pct']:+.1f}%)\n"
            msg += "\n"
        
        # Piores trades (do mês)
        if monthly['worst_trades']:
            msg += "❄️ *PIORES TRADES (30d)*\n"
            for i, trade in enumerate(monthly['worst_trades'], 1):
                msg += f"   {i}. {trade['coin']}: *${trade['pnl']:+.2f}* ({trade['pnl_pct']:+.1f}%)\n"
            msg += "\n"
        
        msg += "⏰ _Atualizado: " + datetime.utcnow().strftime('%d/%m %H:%M') + "_"
        
        return msg
    
    def _format_period(self, period: Dict) -> str:
        """Formata um período específico"""
        realized = period['realized_pnl']
        unrealized = period['unrealized_pnl']
        total = period['total_pnl']
        win_rate = period['win_rate']
        
        # Calcula equity inicial (estimativa)
        equity = self.main_bot.risk_manager.current_equity
        realized_pct = (realized / equity * 100) if equity > 0 else 0
        unrealized_pct = (unrealized / equity * 100) if equity > 0 else 0
        total_pct = (total / equity * 100) if equity > 0 else 0
        
        msg = f"   💰 Realizado: *${realized:+.2f}* ({realized_pct:+.1f}%)\n"
        msg += f"   📈 Não-realizado: *${unrealized:+.2f}* ({unrealized_pct:+.1f}%)\n"
        msg += f"   🎯 Total: *${total:+.2f}* ({total_pct:+.1f}%)\n"
        
        if period['total_trades'] > 0:
            msg += f"   🏆 Win Rate: *{win_rate:.0f}%* ({period['winning_trades']}/{period['total_trades']})\n"
        
        return msg
    
    def add_trade(self, trade: Dict):
        """
        Adiciona trade ao histórico
        
        Args:
            trade: {
                'coin': str,
                'side': 'long' | 'short',
                'entry_price': float,
                'exit_price': float,
                'size': float,
                'pnl': float,
                'pnl_pct': float,
                'opened_at': datetime,
                'closed_at': datetime,
                'closed': bool
            }
        """
        self.trade_history.append(trade)
        
        # Mantém apenas últimos 1000 trades
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
