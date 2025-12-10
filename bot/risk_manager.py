"""
Risk Manager
Gerencia risco, position sizing e limites de trading
"""
import logging
from typing import Optional, Dict, Tuple, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class RiskManager:
    """Gerenciador de Risco para o bot"""
    
    def __init__(self,
                 risk_per_trade_pct: float = 2.0,
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
    
    def can_open_new_trade(self, 
                          current_total_risk_pct: float = 0.0,
                          new_trade_risk_pct: float = 0.0,
                          max_total_risk_pct: float = 100.0) -> Tuple[bool, str]:
        """
        Verifica se pode abrir novo trade
        
        Args:
            current_total_risk_pct: Risco total acumulado das posições abertas em %
            new_trade_risk_pct: Risco estimado do novo trade em %
            max_total_risk_pct: Limite máximo de risco total em %
            
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
        
        # Verifica risco total acumulado
        projected_risk = current_total_risk_pct + new_trade_risk_pct
        if projected_risk > max_total_risk_pct:
             return False, (f"Risco total excederia limite: Atual={current_total_risk_pct:.2f}% + "
                            f"Novo={new_trade_risk_pct:.2f}% = {projected_risk:.2f}% "
                            f"(Max: {max_total_risk_pct}%)")
        
        return True, "OK"
    
    def calculate_position_size(self, 
                                symbol: str, 
                                entry_price: float,
                                stop_loss_pct: float = 2.0,
                                risk_multiplier: float = 1.0,
                                current_total_risk_pct: float = 0.0,
                                max_total_risk_pct: float = 100.0) -> Optional[Dict[str, float]]:
        """
        Calcula tamanho da posição baseado em risco
        
        Args:
            symbol: Par a operar
            entry_price: Preço de entrada
            stop_loss_pct: % de stop loss (ex: 2.0 para -2%)
            risk_multiplier: Multiplicador de risco (default 1.0). Use < 1.0 para reduzir risco (ex: scalp).
            current_total_risk_pct: Risco total já aberto (%)
            max_total_risk_pct: Limite de risco total (%)
            
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
            
        # Calcula quanto vai arriscar neste trade (para validar antes)
        risk_pct_this_trade = self.risk_per_trade_pct * risk_multiplier # Simplificação
        
        # Verifica se pode operar
        can_trade, reason = self.can_open_new_trade(
            current_total_risk_pct=current_total_risk_pct,
            new_trade_risk_pct=risk_pct_this_trade,
            max_total_risk_pct=max_total_risk_pct
        )
        if not can_trade:
            logger.warning(f"{symbol}: Não pode operar - {reason}")
            return None
        
        if entry_price <= 0:
            logger.error(f"{symbol}: Preço de entrada inválido: {entry_price}")
            return None
        
        # ---------------------------------------------------------------------
        # HARD RISK LIMIT (PATCH 2.5%)
        # Limite máximo de risco por operação: 2.5% da equity atual
        # ---------------------------------------------------------------------
        MAX_TRADE_RISK_PCT = 2.5  # 2.5% hard cap
        
        # Risco base proposto
        raw_risk_amount = (self.risk_per_trade_pct / 100) * self.current_equity * risk_multiplier
        
        # Teto de risco
        max_allowed_risk_usd = self.current_equity * (MAX_TRADE_RISK_PCT / 100)
        
        # Verifica e ajusta
        risk_amount = raw_risk_amount
        was_capped = False
        
        if risk_amount > max_allowed_risk_usd:
            logger.warning(
                f"[RISK] ⚠️ Ajustando tamanho para {symbol}: "
                f"Risco proposto ${risk_amount:.2f} > Max permitido ${max_allowed_risk_usd:.2f} (2.5%)"
            )
            risk_amount = max_allowed_risk_usd
            was_capped = True
        else:
            logger.info(
                f"[RISK] Trade {symbol} dentro do limite: "
                f"Risco ${risk_amount:.2f} <= Max ${max_allowed_risk_usd:.2f}"
            )

        # ---------------------------------------------------------------------
        
        if stop_loss_pct <= 0:
            stop_loss_pct = 2.0  # default
        
        # Recalcula position_size com o risk_amount (possivelmente clampado)
        # Risco = Notional * (SL_PCT / 100)
        # Notional = Risco / (SL_PCT / 100)
        # Size = Notional / Entry
        
        notional_value = risk_amount / (stop_loss_pct / 100)
        position_size = notional_value / entry_price
        
        # Calcula leverage necessária
        leverage = notional_value / risk_amount if risk_amount > 0 else 1 # Para stop %, leverage não muda o risco $
        
        # Espera, cálculo de leverage acima está estranho para perp.
        # Leverage = Notional / MarginCollateral.
        # Se eu quero arriscar $X, e meu stop é Y%, então Notional = $X / Y%.
        # Mas quanto de margem eu coloco? 
        # Normalmente definimos Leverage primeiro ou calculamos baseado em quanto queremos alocar de banca?
        # Aqui o bot parece definir leverage dinamicamente para caber o risco.
        # Vamos manter a lógica original: leverage = Notional / risk_amount? NÃO.
        # Original estava: leverage = notional_value / risk_amount.
        # Se stop é 2%, notional = risk / 0.02 = 50 * risk.
        # Logo leverage = 50 * risk / risk = 50x.
        # Isso implica que a margem alocada (Isolated) seria igual ao risk_amount?
        # Se sim, ao tomar stop de 2% com 50x, perde 100% da margem = risk_amount. Faz sentido para Isolated.
        
        leverage_calc = notional_value / risk_amount if risk_amount > 0 else 1
        
        # LIMITA LEVERAGE
        if leverage_calc > self.max_leverage:
            leverage = self.max_leverage
            # Se limitou leverage, e queremos manter o RISK fixo, temos que aumentar a margem?
            # Ou reduzir o size?
            # Se limitarmos leverage, o Notional máximo com aquele Risk Amount (usado como margem) diminui?
            # Se Margin = RiskAmount. MaxNotional = Margin * MaxLev.
            # Então Notional cai. Risco Real = Notional * Stop%.
            # Risco Real = (RiskAmount * MaxLev) * Stop%.
            # Se Stop% * MaxLev < 1 (ex: 2% * 20x = 40%), perdemos 40% da margem apenas. Risco < RiskAmount. OK.
            # Se Stop% * MaxLev > 1 (ex: 2% * 100x = 200%), liquidaria antes.
            
            # Vamos manter a lógica original de re-calculo simples:
            # Se leverage estourou, recalculamos size baseado no max leverage permitido para aquele risk_amount (margem).
            notional_value = self.max_leverage * risk_amount
            position_size = notional_value / entry_price
            logger.info(f"{symbol}: Leverage limitado a {self.max_leverage}x (Mantendo margin/risk fixo)")
            leverage = self.max_leverage
        else:
            leverage = leverage_calc
        
        # Depois verifica MIN_NOTIONAL
        if notional_value < self.min_notional:
            # Se ficou abaixo do mínimo, tentamos aumentar alavancagem se possível?
            # Ou abortamos?
            if was_capped:
                logger.warning(
                    f"[RISK] 🚫 Trade em {symbol} abortado: size ajustado (risco max) menor que mínimo viável. "
                    f"Notional=${notional_value:.2f} < ${self.min_notional}"
                )
                return None
            
            # Lógica legada de tentar subir leverage:
            required_leverage = self.min_notional / risk_amount if risk_amount > 0 else 1
            if required_leverage > self.max_leverage:
                 logger.warning(
                    f"{symbol}: Notional muito baixo (${notional_value:.2f}) mesmo com max leverage. "
                    f"Precisaria {required_leverage:.1f}x. NÃO OPERANDO."
                )
                 return None
            
            leverage = min(required_leverage, self.max_leverage)
            notional_value = risk_amount * leverage
            position_size = notional_value / entry_price
             
        # Round leverage para int
        leverage = int(round(leverage))
        if leverage < 1: leverage = 1
        
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
            f"risk=${risk_amount:.2f} {'(CAPPED)' if was_capped else ''} | sl={stop_loss_pct}%"
        )
        
        return result

    def calculate_position_size_structural(self, 
                                        symbol: str, 
                                        entry_price: float,
                                        stop_price: float,
                                        risk_pct: Optional[float] = None,
                                        current_total_risk_pct: float = 0.0,
                                        max_total_risk_pct: float = 100.0) -> Optional[Dict[str, float]]:
        """
        Calcula tamanho da posição baseado em um stop loss ESTRUTURAL (preço fixo).
        
        Args:
            symbol: Par a operar
            entry_price: Preço de entrada
            stop_price: Preço do stop loss estrutural
            risk_pct: % da banca a arriscar (se None, usa self.risk_per_trade_pct)
            current_total_risk_pct: Risco total já aberto (%)
            max_total_risk_pct: Limite de risco total (%)
            
        Returns:
            Dict com size, notional, leverage ou None se inválido
        """
        if entry_price <= 0 or stop_price <= 0:
            logger.error(f"{symbol}: Preços inválidos: Entry=${entry_price}, Stop=${stop_price}")
            return None
            
        # Determina direção implícita
        is_long = entry_price > stop_price
        
        # Calcula distância do stop em %
        if is_long:
            stop_dist_pct = ((entry_price - stop_price) / entry_price) * 100
        else:
            stop_dist_pct = ((stop_price - entry_price) / entry_price) * 100
            
        # Validações de sanidade do stop estrutural
        if stop_dist_pct < 0.2:
            logger.warning(f"{symbol}: Stop estrutural muito curto ({stop_dist_pct:.2f}%). Mínimo 0.2%. Rejeitando.")
            return None
            
        if stop_dist_pct > 15.0:
            logger.warning(f"{symbol}: Stop estrutural muito longo ({stop_dist_pct:.2f}%). Máximo 15%. Rejeitando.")
            return None
            
        # Usa o método padrão passando a % calculada
        # Ajusta risk_per_trade temporariamente se risk_pct for fornecido
        original_risk = self.risk_per_trade_pct
        if risk_pct is not None:
            self.risk_per_trade_pct = risk_pct
            
        try:
            # Chama o cálculo padrão (que já faz todas as verificações de conta, leverage, notional)
            result = self.calculate_position_size(
                symbol=symbol, 
                entry_price=entry_price, 
                stop_loss_pct=stop_dist_pct,
                risk_multiplier=1.0, # Já estamos passando o risk_pct correto via self.risk_per_trade_pct
                current_total_risk_pct=current_total_risk_pct,
                max_total_risk_pct=max_total_risk_pct
            )
            
            if result:
                result['stop_price_structural'] = stop_price
                logger.info(f"{symbol} [STRUCTURAL] Stop a {stop_dist_pct:.2f}% de distância (${stop_price})")
                
            return result
        finally:
            # Restaura config original
            if risk_pct is not None:
                self.risk_per_trade_pct = original_risk
    
    def get_status(self) -> Dict[str, Any]:
        """
        Retorna status completo de risco para o Telegram
        Compatível com o formato esperado pelo TelegramInteractivePRO
        """
        return {
            'state': 'RUNNING',  # Estados possíveis: RUNNING, COOLDOWN, HALTED_DAILY, HALTED_WEEKLY, HALTED_DRAWDOWN
            'equity_peak': self.current_equity,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_pct': self.daily_drawdown_pct,
            'weekly_pnl': 0.0,  # Não temos tracking semanal neste RiskManager básico
            'weekly_pnl_pct': 0.0,
            'drawdown_pct': min(0, self.daily_drawdown_pct),  # Sempre negativo ou zero
            'losing_streak': 0,  # Não temos tracking de streak
            'cooldown_until': None,
            'limits': {
                'daily_loss_limit_pct': self.max_daily_drawdown_pct,
                'weekly_loss_limit_pct': 15.0,  # Valor default
                'max_drawdown_pct': self.max_daily_drawdown_pct,
                'max_losing_streak': 5  # Valor default
            }
        }
    
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
