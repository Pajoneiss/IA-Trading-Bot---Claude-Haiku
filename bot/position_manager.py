"""
Position Manager
Gerencia posições abertas, stops virtuais e take profits
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Position:
    """Representa uma posição aberta"""
    
    def __init__(self, symbol: str, side: str, entry_price: float, size: float,
                 leverage: int, stop_loss_pct: float, take_profit_pct: float,
                 strategy: str = 'swing'):
        self.symbol = symbol
        self.side = side  # 'long' ou 'short'
        self.entry_price = entry_price
        self.size = size
        self.leverage = leverage
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.strategy = strategy # 'scalp' ou 'swing'
        self.opened_at = datetime.now(timezone.utc)
        
        # Calcula preços de SL e TP
        if side == 'long':
            self.stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
            self.take_profit_price = entry_price * (1 + take_profit_pct / 100)
        else:  # short
            self.stop_loss_price = entry_price * (1 + stop_loss_pct / 100)
            self.take_profit_price = entry_price * (1 - take_profit_pct / 100)
    
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
            elif current_price >= self.take_profit_price:
                return 'take_profit'
        else:  # short
            if current_price >= self.stop_loss_price:
                return 'stop_loss'
            elif current_price <= self.take_profit_price:
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

    def get_unrealized_pnl_usd(self, current_price: float) -> float:
        """Calcula PnL não realizado em USD"""
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
            return 0.0
            
        if self.side == 'long':
            return (current_price - self.entry_price) * self.size
        else:  # short
            return (self.entry_price - current_price) * self.size
    
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
            'opened_at': self.opened_at.isoformat()
        }


class PositionManager:
    """Gerencia posições abertas e stops virtuais"""
    
    def __init__(self, default_stop_pct: float = 2.0, default_tp_pct: float = 4.0):
        """
        Inicializa Position Manager
        
        Args:
            default_stop_pct: Stop loss padrão em % (ex: 2.0 = -2%)
            default_tp_pct: Take profit padrão em % (ex: 4.0 = +4%)
        """
        self.default_stop_pct = default_stop_pct
        self.default_tp_pct = default_tp_pct
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        
        logger.info(f"PositionManager inicializado: SL={default_stop_pct}% | TP={default_tp_pct}%")
    
    def add_position(self, symbol: str, side: str, entry_price: float, 
                     size: float, leverage: int,
                     stop_loss_pct: Optional[float] = None,
                     take_profit_pct: Optional[float] = None,
                     strategy: str = 'swing'):
        """
        Adiciona nova posição ao gerenciamento
        
        Args:
            symbol: Par (ex: BTCUSDC)
            side: 'long' ou 'short'
            entry_price: Preço de entrada
            size: Tamanho da posição
            leverage: Alavancagem usada
            stop_loss_pct: % de stop loss (usa default se None)
            take_profit_pct: % de take profit (usa default se None)
            strategy: 'scalp' ou 'swing'
        """
        if stop_loss_pct is None:
            stop_loss_pct = self.default_stop_pct
        if take_profit_pct is None:
            take_profit_pct = self.default_tp_pct
        
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
            leverage=leverage,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            strategy=strategy
        )
        
        self.positions[symbol] = position
        
        logger.info(
            f"Posição adicionada ({strategy.upper()}): {symbol} {side.upper()} | "
            f"entry=${entry_price:.2f} | size={size} | lev={leverage}x | "
            f"SL=${position.stop_loss_price:.2f} (-{stop_loss_pct}%) | "
            f"TP=${position.take_profit_price:.2f} (+{take_profit_pct}%)"
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
            pos.take_profit_price = new_entry_price * (1 + pos.take_profit_pct / 100)
        else:
            pos.stop_loss_price = new_entry_price * (1 + pos.stop_loss_pct / 100)
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
            
            # Se posição não está sendo gerenciada, adiciona
            if symbol not in self.positions:
                size = abs(float(pos.get('size', 0)))
                if size > 0:  # Ignora posições fechadas
                    side = 'long' if float(pos.get('size', 0)) > 0 else 'short'
                    entry_price = float(pos.get('entry_price', 0))
                    leverage = int(pos.get('leverage', 1))
                    
                    logger.info(f"Sincronizando posição existente da exchange: {symbol}")
                    self.add_position(
                        symbol=symbol,
                        side=side,
                        entry_price=entry_price,
                        size=size,
                        leverage=leverage,
                        strategy='swing' # Assume swing para posições existentes
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
                pos_dict['unrealized_pnl'] = pos.get_unrealized_pnl_usd(current_price)
            else:
                pos_dict['unrealized_pnl_pct'] = 0.0
                pos_dict['unrealized_pnl'] = 0.0
                
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
            
            logger.info(
                f"{symbol} {pos.side.upper()}: "
                f"entry=${pos.entry_price:.2f} | current=${current_price:.2f} | "
                f"PnL={pnl_pct:+.2f}% | SL=${pos.stop_loss_price:.2f} | TP=${pos.take_profit_price:.2f}"
            )
        logger.info("=" * 50)
