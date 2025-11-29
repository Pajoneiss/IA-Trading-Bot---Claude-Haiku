"""
Risk Manager
Gerencia risco, position sizing e limites de trading
"""
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class RiskManager:
    """Gerenciador de Risco para o bot"""
    
    def __init__(self,
                 risk_per_trade_pct: float = 10.0,
                 max_daily_drawdown_pct: float = 10.0,
                 max_open_trades: int = 10,
                 max_leverage: int = 50,
                 min_notional: float = 0.5):
        """
        Inicializa Risk Manager
        
        Args:
            risk_per_trade_pct: % da banca a arriscar por trade (ex: 2.0)
            max_daily_drawdown_pct: Drawdown máximo diário permitido (ex: 10.0)
            max_open_trades: Número máximo de trades abertos simultaneamente
            max_leverage: Alavancagem máxima permitida (ex: 50)
            min_notional: Notional mínimo em USDC (ex: 0.5)
        """
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.max_open_trades = max_open_trades
        self.max_leverage = max_leverage
        self.min_notional = min_notional
        
        # Estado interno
        self.current_equity = 0.0
        self.starting_equity_today = 0.0
        self.daily_pnl = 0.0
        self.daily_drawdown_pct = 0.0
        self.open_positions_count = 0
        self.last_reset_date = datetime.now(timezone.utc).date()
        
        logger.info(f"RiskManager inicializado: risk={risk_per_trade_pct}% | "
                   f"max_dd={max_daily_drawdown_pct}% | max_trades={max_open_trades} | "
                   f"max_lev={max_leverage}x | min_notional=${min_notional}")
    
    def update_equity(self, equity: float, realized_pnl_today: float = 0.0):
        """
        Atualiza equity e calcula drawdown diário
        
        Args:
            equity: Equity total atual da conta (sempre obtido via API)
            realized_pnl_today: PnL realizado hoje (opcional, se disponível)
        """
        current_date = datetime.now(timezone.utc).date()
        
        # Reset diário se mudou o dia
        if current_date > self.last_reset_date:
            logger.info(f"Reset diário: {self.last_reset_date} → {current_date}")
            self.starting_equity_today = equity
            self.daily_pnl = 0.0
            self.daily_drawdown_pct = 0.0
            self.last_reset_date = current_date
        
        # Se é o primeiro update do dia
        if self.starting_equity_today == 0.0:
            self.starting_equity_today = equity
        
        self.current_equity = equity
        
        # Calcula drawdown diário
        if self.starting_equity_today > 0:
            self.daily_pnl = equity - self.starting_equity_today
            self.daily_drawdown_pct = (self.daily_pnl / self.starting_equity_today) * 100
        else:
            self.daily_drawdown_pct = 0.0
        
        logger.debug(f"Equity atualizada: ${equity:.2f} | DD hoje: {self.daily_drawdown_pct:+.2f}%")

    @property
    def daily_pnl_pct(self) -> float:
        """Alias para daily_drawdown_pct (compatibilidade)"""
        return self.daily_drawdown_pct
    
    def update_open_positions(self, count: int):
        """
        Atualiza número de posições abertas
        
        Args:
            count: Número atual de posições abertas
        """
        self.open_positions_count = count
    
    def can_open_new_trade(self) -> Tuple[bool, str]:
        """
        Verifica se pode abrir novo trade
        
        Returns:
            (pode_operar, motivo)
        """
        # Verifica equity
        if self.current_equity <= 0:
            return False, "Equity inválida ou zero"
        
        # Verifica drawdown diário
        if self.daily_drawdown_pct <= -self.max_daily_drawdown_pct:
            return False, f"Drawdown diário excedido: {self.daily_drawdown_pct:.2f}% (limite: -{self.max_daily_drawdown_pct}%)"
        
        # Verifica número de trades abertos
        if self.open_positions_count >= self.max_open_trades:
            return False, f"Máximo de trades abertos atingido: {self.open_positions_count}/{self.max_open_trades}"
        
        return True, "OK"
    
    def calculate_position_size(self, 
                                symbol: str, 
                                entry_price: float,
                                stop_loss_pct: float = 2.0,
                                risk_multiplier: float = 1.0) -> Optional[Dict[str, float]]:
        """
        Calcula tamanho da posição baseado em risco
        
        Args:
            symbol: Par a operar
            entry_price: Preço de entrada
            stop_loss_pct: % de stop loss (ex: 2.0 para -2%)
            risk_multiplier: Multiplicador de risco (default 1.0). Use < 1.0 para reduzir risco (ex: scalp).
            
        Returns:
            Dict com size, notional, leverage ou None se não puder operar
        """
        # Converte entry_price para float com segurança
        try:
            entry_price = float(entry_price)
        except (ValueError, TypeError):
            logger.error(f"{symbol}: Preço de entrada inválido (não é número): {entry_price}")
            return None
        
        # Converte stop_loss_pct para float com segurança
        try:
            stop_loss_pct = float(stop_loss_pct)
        except (ValueError, TypeError):
            stop_loss_pct = 2.0  # default
        
        # Verifica se pode operar
        can_trade, reason = self.can_open_new_trade()
        if not can_trade:
            logger.warning(f"{symbol}: Não pode operar - {reason}")
            return None
        
        if entry_price <= 0:
            logger.error(f"{symbol}: Preço de entrada inválido: {entry_price}")
            return None
        
        # Calcula quanto pode arriscar (em USDC)
        # Aplica multiplicador de risco aqui
        risk_amount = (self.risk_per_trade_pct / 100) * self.current_equity * risk_multiplier
        
        # Calcula position size baseado no stop
        # risk_amount = position_size * entry_price * (stop_loss_pct / 100)
        # position_size = risk_amount / (entry_price * stop_loss_pct / 100)
        
        if stop_loss_pct <= 0:
            stop_loss_pct = 2.0  # default
        
        position_size = risk_amount / (entry_price * (stop_loss_pct / 100))
        notional_value = position_size * entry_price
        
        # Calcula leverage necessária
        leverage = notional_value / risk_amount if risk_amount > 0 else 1
        
        # LIMITA LEVERAGE ANTES DE QUALQUER OUTRA COISA!
        if leverage > self.max_leverage:
            leverage = self.max_leverage
            notional_value = leverage * risk_amount
            position_size = notional_value / entry_price
            logger.info(f"{symbol}: Leverage limitado a {leverage}x")
        
        # Depois verifica MIN_NOTIONAL
        if notional_value < self.min_notional:
            required_leverage = self.min_notional / risk_amount if risk_amount > 0 else 1
            
            if required_leverage > self.max_leverage:
                logger.warning(
                    f"{symbol}: Notional muito baixo (${notional_value:.2f}) mesmo com max leverage. "
                    f"Precisaria {required_leverage:.1f}x mas limite é {self.max_leverage}x. NÃO OPERANDO."
                )
                return None
            
            # Ajusta para atingir min_notional (respeitando max_leverage)
            leverage = min(required_leverage, self.max_leverage)
            notional_value = risk_amount * leverage
            position_size = notional_value / entry_price
            
            logger.info(f"{symbol}: Ajustado para MIN_NOTIONAL: notional=${notional_value:.2f} | lev={leverage:.1f}x")
        
        # Round leverage para int
        leverage = int(round(leverage))
        
        # Arredonda position size para precisão apropriada
        if entry_price > 1000:  # BTC-like
            position_size = round(position_size, 4)
        elif entry_price > 100:  # ETH-like
            position_size = round(position_size, 3)
        else:  # Altcoins
            position_size = round(position_size, 2)
        
        result = {
            'size': position_size,
            'notional': round(notional_value, 2),
            'leverage': leverage,
            'risk_amount_usd': round(risk_amount, 2),
            'stop_loss_pct': stop_loss_pct
        }
        
        logger.info(
            f"{symbol} Position Sizing: size={position_size:.4f} | "
            f"notional=${notional_value:.2f} | lev={leverage}x | "
            f"risk=${risk_amount:.2f} | sl={stop_loss_pct}%"
        )
        
        return result
    
    def get_status_summary(self) -> str:
        """Retorna resumo do status de risco"""
        return (
            f"Equity=${self.current_equity:.2f} | "
            f"DD_hoje={self.daily_drawdown_pct:+.2f}% | "
            f"Posições={self.open_positions_count}/{self.max_open_trades}"
        )
    
    def log_risk_limits(self):
        """Loga limites de risco configurados"""
        logger.info("=== LIMITES DE RISCO ===")
        logger.info(f"Risco por trade: {self.risk_per_trade_pct}%")
        logger.info(f"Max DD diário: {self.max_daily_drawdown_pct}%")
        logger.info(f"Max trades simultâneos: {self.max_open_trades}")
        logger.info(f"Max leverage: {self.max_leverage}x")
        logger.info(f"Min notional: ${self.min_notional}")
        logger.info("========================")
