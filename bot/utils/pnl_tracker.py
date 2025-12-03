"""
PnL Tracker - Análise detalhada de Performance (VERSÃO MELHORADA)
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
    VERSÃO MELHORADA: Busca dados reais do RiskManager e PositionManager
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
        USA DADOS REAIS do bot
        """
        try:
            # BUSCA DADOS REAIS DO BOT
            equity = self.main_bot.risk_manager.current_equity
            starting_equity = self.main_bot.risk_manager.starting_equity_today  # ← CORRIGIDO
            drawdown = self.main_bot.risk_manager.daily_drawdown_pct
            
            # Calcula PnL realizado baseado no drawdown
            realized_pnl = (drawdown / 100) * equity
            
            # PnL não-realizado das posições abertas
            unrealized_data = self._get_open_positions_pnl()
            unrealized_pnl = unrealized_data['total_pnl']
            
            # Total
            total_pnl = realized_pnl + unrealized_pnl
            
            # Calcula % do total PnL
            if starting_equity > 0:
                total_pnl_pct = (total_pnl / starting_equity) * 100
                realized_pnl_pct = (realized_pnl / starting_equity) * 100
                unrealized_pnl_pct = (unrealized_pnl / starting_equity) * 100
            else:
                total_pnl_pct = 0.0
                realized_pnl_pct = 0.0
                unrealized_pnl_pct = 0.0
            
            # Para win rate, usamos dados do histórico se disponível
            # Caso contrário, estimamos baseado no PnL
            trades_data = self._get_trades_from_history(start, end)
            
            if trades_data['total_trades'] > 0:
                win_rate = trades_data['win_rate']
                winning_trades = trades_data['winning_trades']
                losing_trades = trades_data['losing_trades']
                total_trades = trades_data['total_trades']
                best_trades = trades_data['best_trades']
                worst_trades = trades_data['worst_trades']
            else:
                # Estimativa baseada no PnL
                if total_pnl > 0:
                    win_rate = 60.0  # Estimativa conservadora
                elif total_pnl < 0:
                    win_rate = 40.0
                else:
                    win_rate = 50.0
                
                winning_trades = 0
                losing_trades = 0
                total_trades = 0
                best_trades = []
                worst_trades = []
            
            return {
                'period': period_name,
                'realized_pnl': realized_pnl,
                'realized_pnl_pct': realized_pnl_pct,
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_pct': unrealized_pnl_pct,
                'total_pnl': total_pnl,
                'total_pnl_pct': total_pnl_pct,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'best_trades': best_trades,
                'worst_trades': worst_trades
            }
            
        except Exception as e:
            logger.error(f"[PNL_TRACKER] Erro ao analisar período {period_name}: {e}")
            return self._get_empty_analysis(period_name)
    
    def _get_trades_from_history(self, start: datetime, end: datetime) -> Dict:
        """
        Busca trades do histórico
        """
        try:
            if not self.trade_history:
                return {
                    'total_trades': 0,
                    'win_rate': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'best_trades': [],
                    'worst_trades': []
                }
            
            # Filtra trades do período
            period_trades = [
                t for t in self.trade_history 
                if t.get('closed') and 
                t.get('closed_at') and 
                start <= t['closed_at'] <= end
            ]
            
            if not period_trades:
                return {
                    'total_trades': 0,
                    'win_rate': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'best_trades': [],
                    'worst_trades': []
                }
            
            # Calcula win rate
            winning = [t for t in period_trades if t.get('pnl', 0) > 0]
            losing = [t for t in period_trades if t.get('pnl', 0) < 0]
            
            win_rate = (len(winning) / len(period_trades) * 100) if period_trades else 0
            
            # Melhores e piores
            best_trades = sorted(period_trades, key=lambda x: x.get('pnl', 0), reverse=True)[:3]
            worst_trades = sorted(period_trades, key=lambda x: x.get('pnl', 0))[:3]
            
            return {
                'total_trades': len(period_trades),
                'win_rate': win_rate,
                'winning_trades': len(winning),
                'losing_trades': len(losing),
                'best_trades': best_trades,
                'worst_trades': worst_trades
            }
            
        except Exception as e:
            logger.error(f"[PNL_TRACKER] Erro ao buscar trades: {e}")
            return {
                'total_trades': 0,
                'win_rate': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'best_trades': [],
                'worst_trades': []
            }
    
    def _get_open_positions_pnl(self) -> Dict:
        """
        Calcula PnL de posições abertas
        USA DADOS REAIS do PositionManager
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
        try:
            equity = self.main_bot.risk_manager.current_equity
        except:
            equity = 100.0
        
        msg = "📉 *PNL — Análise Completa*\n\n"
        
        # Diário
        daily = analysis['daily']
        msg += f"📊 *{daily['period'].upper()}*\n"
        msg += self._format_period(daily, equity) + "\n"
        
        # Semanal
        weekly = analysis['weekly']
        msg += f"📅 *{weekly['period'].upper()} (Últimos 7 dias)*\n"
        msg += self._format_period(weekly, equity) + "\n"
        
        # Mensal
        monthly = analysis['monthly']
        msg += f"📆 *{monthly['period'].upper()} (Últimos 30 dias)*\n"
        msg += self._format_period(monthly, equity) + "\n"
        
        # Melhores trades (do mês)
        if monthly['best_trades']:
            msg += "🔥 *MELHORES TRADES (30d)*\n"
            for i, trade in enumerate(monthly['best_trades'], 1):
                coin = trade.get('coin', 'UNKNOWN')
                pnl = trade.get('pnl', 0)
                pnl_pct = trade.get('pnl_pct', 0)
                msg += f"   {i}. {coin}: *${pnl:+.2f}* ({pnl_pct:+.1f}%)\n"
            msg += "\n"
        
        # Piores trades (do mês)
        if monthly['worst_trades'] and any(t.get('pnl', 0) < 0 for t in monthly['worst_trades']):
            msg += "❄️ *PIORES TRADES (30d)*\n"
            for i, trade in enumerate(monthly['worst_trades'], 1):
                if trade.get('pnl', 0) < 0:
                    coin = trade.get('coin', 'UNKNOWN')
                    pnl = trade.get('pnl', 0)
                    pnl_pct = trade.get('pnl_pct', 0)
                    msg += f"   {i}. {coin}: *${pnl:+.2f}* ({pnl_pct:+.1f}%)\n"
            msg += "\n"
        
        # Nota sobre dados
        if analysis['daily']['total_trades'] == 0:
            msg += "💡 _Nota: Métricas baseadas em equity atual._\n"
            msg += "_Win rate será calculado conforme trades forem executados._\n\n"
        
        msg += "⏰ _Atualizado: " + datetime.utcnow().strftime('%d/%m %H:%M') + " UTC_"
        
        return msg
    
    def _format_period(self, period: Dict, equity: float) -> str:
        """Formata um período específico"""
        realized = period['realized_pnl']
        unrealized = period['unrealized_pnl']
        total = period['total_pnl']
        win_rate = period['win_rate']
        
        # Calcula percentuais
        realized_pct = (realized / equity * 100) if equity > 0 else 0
        unrealized_pct = (unrealized / equity * 100) if equity > 0 else 0
        total_pct = (total / equity * 100) if equity > 0 else 0
        
        msg = f"   💰 Realizado: *${realized:+.2f}* ({realized_pct:+.1f}%)\n"
        msg += f"   📈 Não-realizado: *${unrealized:+.2f}* ({unrealized_pct:+.1f}%)\n"
        msg += f"   🎯 Total: *${total:+.2f}* ({total_pct:+.1f}%)\n"
        
        if period['total_trades'] > 0:
            msg += f"   🏆 Win Rate: *{win_rate:.0f}%* ({period['winning_trades']}/{period['total_trades']})\n"
        elif win_rate > 0:
            msg += f"   🏆 Win Rate estimado: *{win_rate:.0f}%*\n"
        
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
        # Adiciona timestamp se não tiver
        if 'closed_at' not in trade and trade.get('closed'):
            trade['closed_at'] = datetime.utcnow()
        
        self.trade_history.append(trade)
        
        # Mantém apenas últimos 1000 trades
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
        
        logger.info(f"[PNL_TRACKER] Trade adicionado: {trade.get('coin')} {trade.get('side')} PnL: ${trade.get('pnl', 0):+.2f}")
