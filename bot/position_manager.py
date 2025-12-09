import json
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from bot.position_state import TradeState, ManagementProfile

logger = logging.getLogger(__name__)


class Position:
    """Representa uma posição aberta"""
    
    def __init__(self, symbol: str, side: str, entry_price: float, size: float,
                 leverage: int, stop_loss_pct: float, 
                 take_profit_pct: Optional[float] = None, # PATCH: TP Opcional
                 strategy: str = 'swing',
                 initial_stop_price: Optional[float] = None,
                 management_profile: str = "SCALP_CAN_PROMOTE"):
        self.symbol = symbol
        self.side = side  # 'long' ou 'short'
        self.entry_price = entry_price
        self.size = size
        self.leverage = leverage
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.take_profit_price: Optional[float] = None # Inicializa explicitamente
        self.strategy = strategy # 'scalp' ou 'swing'
        self.opened_at = datetime.now(timezone.utc)
        
        # Novos campos Position Manager 2.0
        self.trade_state = TradeState.INIT
        try:
            self.management_profile = ManagementProfile(management_profile)
        except:
            self.management_profile = ManagementProfile.SCALP_CAN_PROMOTE
            
        self.locked_in_profit = 0.0
        
        # Calcula preços de SL e TP
        if side == 'long':
            self.stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
            if take_profit_pct is not None:
                self.take_profit_price = entry_price * (1 + take_profit_pct / 100)
        else:  # short
            self.stop_loss_price = entry_price * (1 + stop_loss_pct / 100)
            if take_profit_pct is not None:
                self.take_profit_price = entry_price * (1 - take_profit_pct / 100)

        # Se stop inicial explícito for fornecido, usa ele (prioridade sobre pct)
        if initial_stop_price and initial_stop_price > 0:
            self.stop_loss_price = initial_stop_price
            # Recalcula pct para consistência visual
            diff = abs(entry_price - initial_stop_price)
            self.stop_loss_pct = (diff / entry_price) * 100

        # Salva o stop inicial para cálculo de R
        self.initial_stop_price_fixed = self.stop_loss_price
            
    def calculate_current_r(self, current_price: float) -> float:
        """Calcula quantos R o trade andou"""
        risk_unit = abs(self.entry_price - self.initial_stop_price_fixed)
        if risk_unit == 0:
            return 0.0
            
        if self.side == 'long':
            return (current_price - self.entry_price) / risk_unit
        else:
            return (self.entry_price - current_price) / risk_unit
    
    def check_exit(self, current_price: float) -> Optional[str]:
        """
        Verifica se deve fechar posição
        
        Args:
            current_price: Preço atual do ativo
            
        Returns:
            'stop_loss', 'take_profit' ou None
        """
        if self.side == 'long':
            if current_price <= self.stop_loss_price:
                return 'stop_loss'
            # PATCH: Só verifica TP se ele existir
            elif (self.take_profit_price is not None and 
                  self.trade_state != TradeState.PROMOTED_TO_SWING and 
                  current_price >= self.take_profit_price):
                return 'take_profit'
        else:  # short
            if current_price >= self.stop_loss_price:
                return 'stop_loss'
            elif (self.take_profit_price is not None and 
                  self.trade_state != TradeState.PROMOTED_TO_SWING and 
                  current_price <= self.take_profit_price):
                return 'take_profit'
        
        return None
    
    def get_unrealized_pnl_pct(self, current_price: float) -> float:
        """Calcula PnL não realizado em %"""
        # Converte current_price para float com segurança
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
            return 0.0  # Se não conseguir converter, retorna 0
        
        if self.side == 'long':
            return ((current_price - self.entry_price) / self.entry_price) * 100
        else:  # short
            return ((self.entry_price - current_price) / self.entry_price) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dict"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'size': self.size,
            'leverage': self.leverage,
            'stop_loss_price': self.stop_loss_price,
            'take_profit_price': self.take_profit_price,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'strategy': self.strategy,
            'opened_at': self.opened_at.isoformat(),
            'trade_state': self.trade_state.value,
            'management_profile': self.management_profile.value,
            'initial_stop_price_fixed': self.initial_stop_price_fixed
        }


class PositionManager:
    """Gerencia posições abertas e stops virtuais"""
    
    def __init__(self, default_stop_pct: float = 2.0, default_tp_pct: Optional[float] = None):
        """
        Inicializa Position Manager
        
        Args:
            default_stop_pct: Stop loss padrão em % (ex: 2.0 = -2%)
            default_tp_pct: Take profit padrão em % (None = desativado por padrão)
        """
        self.default_stop_pct = default_stop_pct
        self.default_tp_pct = default_tp_pct
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.management_config = self._load_management_config()
        
        tp_log = f"{default_tp_pct}%" if default_tp_pct else "DYNAMIC (PM 2.0)"
        logger.info(f"PositionManager inicializado: SL={default_stop_pct}% | TP={tp_log}")

    def _load_management_config(self) -> Dict[str, Any]:
        """Carrega configurações de gestão"""
        try:
            path = os.path.join("data", "management_config.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar management_config.json: {e}")
        return {}
    
    def add_position(self, symbol: str, side: str, entry_price: float, 
                     size: float, leverage: int,
                     stop_loss_pct: Optional[float] = None,
                     take_profit_pct: Optional[float] = None,
                     strategy: str = 'swing',
                     initial_stop_price: Optional[float] = None,
                     management_profile: str = "SCALP_CAN_PROMOTE"):
        """
        Adiciona nova posição ao gerenciamento
        """
        if stop_loss_pct is None:
            stop_loss_pct = self.default_stop_pct
            
        # PATCH: NÃO forza default_tp_pct se ele for None.
        # Permite TP None para gestão dinâmica
        if take_profit_pct is None and self.default_tp_pct is not None:
             take_profit_pct = self.default_tp_pct
        
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
            leverage=leverage,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            strategy=strategy,
            initial_stop_price=initial_stop_price,
            management_profile=management_profile
        )
        
        self.positions[symbol] = position
        
        # Log diferenciado se tem TP ou não
        tp_info = f"TP=${position.take_profit_price:.2f}" if position.take_profit_price else "TP=DYNAMIC"
        
        logger.info(
            f"Posição adicionada ({strategy.upper()}): {symbol} {side.upper()} | "
            f"entry=${entry_price:.2f} | size={size} | lev={leverage}x | "
            f"SL=${position.stop_loss_price:.2f} | {tp_info} | "
            f"Risco Ini: {abs(entry_price - position.stop_loss_price):.4f}"
        )
    
    def update_position(self, symbol: str, new_size: float, new_entry_price: float):
        """
        Atualiza tamanho e preço médio de uma posição existente (DCA/Parcial)
        """
        if symbol not in self.positions:
            return
            
        pos = self.positions[symbol]
        old_size = pos.size
        old_entry = pos.entry_price
        
        pos.size = new_size
        pos.entry_price = new_entry_price
        
        # Recalcula SL/TP baseados no novo preço médio
        if pos.side == 'long':
            pos.stop_loss_price = new_entry_price * (1 - pos.stop_loss_pct / 100)
            if pos.take_profit_pct is not None:
                pos.take_profit_price = new_entry_price * (1 + pos.take_profit_pct / 100)
        else:
            pos.stop_loss_price = new_entry_price * (1 + pos.stop_loss_pct / 100)
            if pos.take_profit_pct is not None:
                pos.take_profit_price = new_entry_price * (1 - pos.take_profit_pct / 100)
            
        logger.info(
            f"Posição atualizada: {symbol} | "
            f"Size: {old_size} -> {new_size} | "
            f"Entry: ${old_entry:.2f} -> ${new_entry_price:.2f}"
        )
    
    def remove_position(self, symbol: str):
        """Remove posição do gerenciamento"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"Posição removida: {symbol}")
    
    def manage_position(self, symbol: str, current_price: float, 
                       current_mode: str, market_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Gerencia proativamente a posição (Position Manager 2.0)
        
        Args:
            symbol: Símbolo
            current_price: Preço atual
            current_mode: Modo de trading (CONSERVADOR, BALANCEADO, AGRESSIVO)
            market_context: Dados de mercado (indicadores, estrutura, etc)
            
        Returns:
            Lista de ações de gestão (partial_close, update_stop, etc)
        """
        position = self.positions.get(symbol)
        if not position:
            return []
            
        actions = []
        
        # 0. Garante Profile e Config
        profile_key = position.management_profile.value
        mode_key = current_mode
        
        # Fallback de config
        mode_config = self.management_config.get(mode_key, self.management_config.get("BALANCEADO", {}))
        profile_config = mode_config.get(profile_key, mode_config.get("SCALP_CAN_PROMOTE", {}))
        
        # Defaults seguros se json falhar
        first_trim_rr = profile_config.get("first_trim_rr", 1.5)
        first_trim_pct = profile_config.get("first_trim_pct", 0.3)
        promotion_rr = profile_config.get("promotion_rr_min", 2.0)
        be_rr = profile_config.get("be_rr", 1.0)
        
        # 1. Calcula R atual
        current_r = position.calculate_current_r(current_price)
        
        # Logger de debug ocasional (evitar spam)
        # logger.debug(f"{symbol} R={current_r:.2f} State={position.trade_state.value}")

        # === FASE 1: INIT -> Parcial + BE ===
        if position.trade_state == TradeState.INIT:
            if current_r >= first_trim_rr:
                # Ação 1: Parcial
                actions.append({
                    'symbol': symbol,
                    'action': 'partial_close',
                    'percent': first_trim_pct,
                    'reason': f"partial_target_1 ({current_r:.2f}R)",
                    'current_r': current_r
                })
                
                # Ação 2: Mover para Break Even (ou levemente positivo)
                # Protege spread/taxas: Entry +/- 0.1% apenas se BE for pior que stop atual
                side_mult = 1 if position.side == 'long' else -1
                be_price = position.entry_price * (1 + 0.001 * side_mult) # 0.1% profit
                
                # Só move se o novo stop for "melhor" que o atual (mais alto pra long, mais baixo pra short)
                better_stop = False
                if position.side == 'long':
                    if be_price > position.stop_loss_price:
                        better_stop = True
                else:
                    if be_price < position.stop_loss_price:
                        better_stop = True
                        
                if better_stop and current_r >= be_rr:
                    actions.append({
                        'symbol': symbol,
                        'action': 'update_stop',
                        'price': be_price,
                        'reason': 'move_to_breakeven'
                    })
                    position.stop_loss_price = be_price
                
                # Atualiza estado
                position.trade_state = TradeState.SCALP_ACTIVE
                position.locked_in_profit = position.size * first_trim_pct # Estimativa
                
                logger.info(f"⚡ {symbol}: FASE 1 CONCLUÍDA. R={current_r:.2f}. Parcial + BE.")
        
        # === FASE 2: SCALP_ACTIVE -> Promoção ou Saída ===
        elif position.trade_state == TradeState.SCALP_ACTIVE:
            # Opção A: Promoção para Swing
            if position.management_profile != ManagementProfile.SCALP_ONLY and current_r >= promotion_rr:
                # Analisa contexto para promover
                trend = market_context.get('trend', {})
                direction = trend.get('direction', 'neutral')
                strength = trend.get('strength', 0)
                
                # Se tendencia favorável e forte
                aligned = False
                if position.side == 'long' and direction == 'bullish' and strength > 20:
                    aligned = True
                elif position.side == 'short' and direction == 'bearish' and strength > 20:
                    aligned = True
                    
                if aligned:
                    # PROMOÇÃO!
                    position.trade_state = TradeState.PROMOTED_TO_SWING
                    actions.append({
                        'symbol': symbol,
                        'action': 'promote_to_swing',
                        'reason': f"context_aligned_strength_{strength:.0f}"
                    })
                    logger.info(f"🚀 {symbol}: PROMOVIDO A SWING RUNNER! R={current_r:.2f}")
            
            # Opção B: Segundo Alvo (se Scalp Only ou não promoveu)
            second_trim_rr = profile_config.get("second_trim_rr", 2.5)
            if current_r >= second_trim_rr:
                # Fecha quase tudo ou tudo
                actions.append({
                    'symbol': symbol,
                    'action': 'partial_close',
                    'percent': 0.5, # Fecha mais metade do que sobrou
                    'reason': f"scalp_target_2 ({current_r:.2f}R)"
                })
        
        # === FASE 3: TRAILING STOP (Runners) ===
        elif position.trade_state == TradeState.PROMOTED_TO_SWING:
            trail_style = profile_config.get("trail_style", "STRUCTURE")
            offset_factor = profile_config.get("trail_offset_factor", 0.5)
            
            new_stop = None
            
            # Lógica simples de trailing baseada em preço atual para demonstração
            # Idealmente usaria dados históricos de candles passados no market_context
            
            # Trailing via EMA (se disponível)
            indicators = market_context.get('indicators', {})
            ema21 = indicators.get('ema_21')
            
            if trail_style == "EMA" and ema21:
                # Long: Stop abaixo da EMA21
                if position.side == 'long' and current_price > ema21:
                    stop_candidate = ema21 * (1 - offset_factor/100)
                    if stop_candidate > position.stop_loss_price:
                        new_stop = stop_candidate
                # Short: Stop acima da EMA21
                elif position.side == 'short' and current_price < ema21:
                    stop_candidate = ema21 * (1 + offset_factor/100)
                    if stop_candidate < position.stop_loss_price:
                        new_stop = stop_candidate

            # Trailing via Estrutura (Simplificado - usa mínimas/máximas recentes se disponíveis)
            # Como fallback, usa trailing percentual dinâmico do preço (ATR proxy) if structure not avail
            if not new_stop:
                # Fallback trailing
                trail_dist = position.entry_price * (trail_style == "STRUCTURE" and 0.015 or 0.02) # 1.5% ou 2%
                
                if position.side == 'long':
                    candidate = current_price - trail_dist
                    if candidate > position.stop_loss_price:
                        new_stop = candidate
                else:
                    candidate = current_price + trail_dist
                    if candidate < position.stop_loss_price:
                        new_stop = candidate
            
            if new_stop:
                # Validar distância mínima (evitar violino)
                dist_pct = abs(current_price - new_stop) / current_price * 100
                if dist_pct > 0.2: # Mínimo 0.2% de distância
                    actions.append({
                        'symbol': symbol,
                        'action': 'update_stop',
                        'price': new_stop,
                        'reason': f"trailing_{trail_style}"
                    })
                    position.stop_loss_price = new_stop
                    logger.info(f"⛓️ {symbol} Trailing Stop Ajustado: ${new_stop:.2f} (Dist: {dist_pct:.2f}%)")

        return actions
    
    def check_stops(self, current_prices: Dict[str, float]) -> List[Dict[str, str]]:
        """
        Verifica stops de todas as posições
        
        Args:
            current_prices: Dict {symbol: current_price}
            
        Returns:
            Lista de ações a tomar: [{'symbol': 'BTC', 'action': 'close', 'reason': 'stop_loss'}]
        """
        actions = []
        
        for symbol, position in list(self.positions.items()):
            current_price = current_prices.get(symbol)
            
            if current_price is None:
                logger.warning(f"{symbol}: Preço atual não disponível, pulando verificação")
                continue
            
            # Converte para float com segurança
            try:
                current_price = float(current_price)
            except (ValueError, TypeError):
                logger.warning(f"{symbol}: Preço inválido ({current_price}), pulando verificação")
                continue
            
            exit_reason = position.check_exit(current_price)
            
            if exit_reason:
                pnl_pct = position.get_unrealized_pnl_pct(current_price)
                
                logger.warning(
                    f"⚠️  {symbol} {exit_reason.upper()}! "
                    f"Preço atual ${current_price:.2f} | "
                    f"Entry ${position.entry_price:.2f} | "
                    f"PnL: {pnl_pct:+.2f}%"
                )
                
                actions.append({
                    'symbol': symbol,
                    'action': 'close',
                    'reason': exit_reason,
                    'side': position.side,
                    'current_price': current_price,
                    'pnl_pct': pnl_pct
                })
        
        return actions
    
    def sync_with_exchange(self, exchange_positions: List[Dict[str, Any]]):
        """
        Sincroniza posições gerenciadas com posições reais da exchange
        
        Args:
            exchange_positions: Lista de posições da exchange
        """
        exchange_symbols = set()
        
        for pos in exchange_positions:
            symbol = pos.get('coin')
            if not symbol:
                continue
            
            exchange_symbols.add(symbol)
            
            # Se posição não está sendo gerenciada, adiciona (Trade Manual ou Restart)
            if symbol not in self.positions:
                size = abs(float(pos.get('size', 0)))
                if size > 0:  # Ignora posições fechadas
                    side = 'long' if float(pos.get('size', 0)) > 0 else 'short'
                    entry_price = float(pos.get('entry_price', 0))
                    leverage = int(pos.get('leverage', 1))
                    
                    logger.info(f"📥 Detectada nova posição na exchange (MANUAL/RESTART): {symbol}")
                    
                    # Tenta inferir stop se possível (ou usa padrão 2%)
                    # TODO: Futuramente buscar ordens abertas para ver se tem SL real
                    
                    self.add_position(
                        symbol=symbol,
                        side=side,
                        entry_price=entry_price,
                        size=size,
                        leverage=leverage,
                        strategy='manual',
                        management_profile="SCALP_CAN_PROMOTE", # Default para manual
                        stop_loss_pct=self.default_stop_pct # Fallback seguro
                    )
        
        # Remove posições gerenciadas que não existem mais na exchange
        managed_symbols = set(self.positions.keys())
        closed_symbols = managed_symbols - exchange_symbols
        
        for symbol in closed_symbols:
            logger.info(f"Posição {symbol} não existe mais na exchange, removendo do gerenciamento")
            self.remove_position(symbol)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Retorna posição gerenciada"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Verifica se tem posição aberta no símbolo"""
        return symbol in self.positions
    
    def get_all_positions(self, current_prices: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """
        Retorna todas as posições como lista de dicts
        
        Args:
            current_prices: Dict opcional com preços atuais para calcular PnL
        """
        positions_list = []
        for pos in self.positions.values():
            pos_dict = pos.to_dict()
            
            if current_prices:
                current_price = current_prices.get(pos.symbol, pos.entry_price)
                # Garante float
                try:
                    current_price = float(current_price)
                except:
                    current_price = pos.entry_price
                    
                pos_dict['unrealized_pnl_pct'] = pos.get_unrealized_pnl_pct(current_price)
            else:
                pos_dict['unrealized_pnl_pct'] = 0.0
                
            positions_list.append(pos_dict)
            
        return positions_list
    
    def get_positions_count(self) -> int:
        """Retorna número de posições abertas"""
        return len(self.positions)
    
    def log_positions_summary(self, current_prices: Dict[str, float]):
        """Loga resumo de todas as posições"""
        if not self.positions:
            logger.info("Nenhuma posição aberta")
            return
        
        logger.info(f"=== POSIÇÕES ABERTAS ({len(self.positions)}) ===")
        for symbol, pos in self.positions.items():
            current_price = current_prices.get(symbol, pos.entry_price)
            
            # Converte para float com segurança
            try:
                current_price = float(current_price)
            except (ValueError, TypeError):
                current_price = pos.entry_price
            
            pnl_pct = pos.get_unrealized_pnl_pct(current_price)
            
            tp_str = f"${pos.take_profit_price:.2f}" if pos.take_profit_price else "DYNAMIC"
            
            logger.info(
                f"{symbol} {pos.side.upper()}: "
                f"entry=${pos.entry_price:.2f} | current=${current_price:.2f} | "
                f"PnL={pnl_pct:+.2f}% | SL=${pos.stop_loss_price:.2f} | TP={tp_str}"
            )
        logger.info("=" * 50)

    def sync_with_exchange(self, exchange_positions: List[Dict[str, Any]]):
        """
        Sincroniza posições gerenciadas com posições reais da exchange
        
        Args:
            exchange_positions: Lista de posições da exchange
        """
        exchange_symbols = set()
        
        for pos in exchange_positions:
            symbol = pos.get('coin')
            if not symbol:
                continue
            
            exchange_symbols.add(symbol)
            
            # Se posição não está sendo gerenciada, adiciona (Trade Manual ou Restart)
            if symbol not in self.positions:
                size = abs(float(pos.get('size', 0)))
                if size > 0:  # Ignora posições fechadas
                    side = 'long' if float(pos.get('size', 0)) > 0 else 'short'
                    entry_price = float(pos.get('entry_price', 0))
                    leverage = int(pos.get('leverage', 1))
                    
                    # PATCH: Log mais explícito sobre gestão
                    logger.info(
                        f"📥 Detectada nova posição (MANUAL/RESTART) {symbol}: "
                        f"Gerenciada pelo Position Manager 2.0 (Dynamic)."
                    )
                    
                    # Tenta inferir stop se possível (ou usa padrão 2%)
                    # TODO: Futuramente buscar ordens abertas para ver se tem SL real
                    
                    self.add_position(
                        symbol=symbol,
                        side=side,
                        entry_price=entry_price,
                        size=size,
                        leverage=leverage,
                        strategy='manual',
                        management_profile="SCALP_CAN_PROMOTE", # Default para manual
                        stop_loss_pct=self.default_stop_pct, # Fallback seguro
                        take_profit_pct=None # IMPORTANTE: Sem TP fixo sintético!
                    )
        
        # Remove posições gerenciadas que não existem mais na exchange
        managed_symbols = set(self.positions.keys())
        closed_symbols = managed_symbols - exchange_symbols
        
        for symbol in closed_symbols:
            logger.info(f"Posição {symbol} não existe mais na exchange, removendo do gerenciamento")
            self.remove_position(symbol)
