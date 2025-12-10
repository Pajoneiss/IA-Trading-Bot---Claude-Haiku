"""
AI Budget Manager - Controle de Orçamento de Chamadas de IA

PATCH v3.0:
- Limita chamadas diárias de Claude e OpenAI
- Implementa cooldowns entre chamadas
- Reseta contadores automaticamente a cada dia
- Logs detalhados de uso e bloqueios
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AICallRecord:
    """Registro de uma chamada de IA"""
    timestamp: datetime
    reason: str
    symbol: str
    timeframe: str


@dataclass 
class AIBudgetState:
    """Estado atual do orçamento de IA"""
    date: str  # YYYY-MM-DD
    claude_calls: int = 0
    openai_calls: int = 0
    claude_last_call: Optional[datetime] = None
    openai_last_call: Optional[datetime] = None
    claude_history: list = field(default_factory=list)
    openai_history: list = field(default_factory=list)


class AIBudgetManager:
    """
    Gerenciador de Orçamento de IA
    
    Controla:
    - Limite diário de chamadas Claude/OpenAI
    - Cooldowns mínimos entre chamadas
    - Logs de uso e alertas
    - Reset automático diário
    """
    
    CONFIG_FILE = "data/ai_budget_config.json"
    
    def __init__(self, logger_instance=None):
        self.log = logger_instance or logger
        self.config = self._load_config()
        self.state = AIBudgetState(date=self._get_today())
        
        # Extrai configs
        self.enabled = self.config.get("enabled", True)
        daily = self.config.get("daily_budget", {})
        self.claude_max = daily.get("claude_max_calls", 12)
        self.openai_max = daily.get("openai_max_calls", 40)
        
        cooldowns = self.config.get("cooldowns", {})
        self.claude_cooldown_min = cooldowns.get("min_minutes_between_claude_calls", 60)
        self.openai_cooldown_min = cooldowns.get("min_minutes_between_openai_calls", 10)
        
        logging_cfg = self.config.get("logging", {})
        self.log_prefix = logging_cfg.get("log_prefix", "[AI BUDGET]")
        self.warn_pct = logging_cfg.get("warn_when_reach_pct", 0.8)
        self.debug = logging_cfg.get("debug", False)
        
        # Símbolos permitidos
        self.swing_symbols = self.config.get("swing", {}).get("symbols", ["BTC", "ETH"])
        self.scalp_symbols = self.config.get("scalp", {}).get("symbols", ["BTC", "ETH", "SOL"])
        
        self.log.info(f"{self.log_prefix} Inicializado: Claude={self.claude_max}/dia, OpenAI={self.openai_max}/dia")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carrega configuração do arquivo JSON"""
        try:
            config_path = Path(self.CONFIG_FILE)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                self.log.warning(f"{self.log_prefix} Config não encontrada: {self.CONFIG_FILE}")
                return {}
        except Exception as e:
            self.log.error(f"{self.log_prefix} Erro ao carregar config: {e}")
            return {}
    
    def _get_today(self) -> str:
        """Retorna data de hoje em formato YYYY-MM-DD"""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    def _check_day_rollover(self):
        """Verifica se virou o dia e reseta contadores se necessário"""
        today = self._get_today()
        if self.state.date != today:
            self.log.info(f"{self.log_prefix} 🔄 Novo dia detectado! Resetando contadores...")
            self.log.info(f"{self.log_prefix} Ontem: Claude={self.state.claude_calls}, OpenAI={self.state.openai_calls}")
            
            # Reset
            self.state = AIBudgetState(date=today)
            self.log.info(f"{self.log_prefix} ✅ Contadores resetados para {today}")
    
    def _check_warn_threshold(self, call_type: str, current: int, max_val: int):
        """Verifica e loga aviso se atingiu threshold de alerta"""
        if max_val > 0:
            usage_pct = current / max_val
            if usage_pct >= self.warn_pct:
                self.log.warning(
                    f"{self.log_prefix} ⚠️ {call_type} atingiu {usage_pct:.0%} do orçamento "
                    f"({current}/{max_val})"
                )
    
    def _is_cooldown_ok(self, last_call: Optional[datetime], cooldown_minutes: int) -> bool:
        """Verifica se o cooldown passou"""
        if last_call is None:
            return True
        
        now = datetime.now(timezone.utc)
        # Garante timezone
        if last_call.tzinfo is None:
            last_call = last_call.replace(tzinfo=timezone.utc)
        
        elapsed = (now - last_call).total_seconds() / 60
        return elapsed >= cooldown_minutes
    
    def _minutes_until_cooldown_ok(self, last_call: Optional[datetime], cooldown_minutes: int) -> float:
        """Retorna minutos restantes até cooldown liberar"""
        if last_call is None:
            return 0
        
        now = datetime.now(timezone.utc)
        if last_call.tzinfo is None:
            last_call = last_call.replace(tzinfo=timezone.utc)
        
        elapsed = (now - last_call).total_seconds() / 60
        remaining = cooldown_minutes - elapsed
        return max(0, remaining)
    
    # ==================== CLAUDE (SWING) ====================
    
    def can_call_claude(self, reason: str, symbol: str, timeframe: str) -> bool:
        """
        Verifica se pode chamar Claude (IA Swing)
        
        Args:
            reason: Motivo da chamada (ex: "DAILY_EMA_SHIFT", "REGIME_CHANGE")
            symbol: Símbolo (ex: "BTC", "ETH")
            timeframe: Timeframe (ex: "4h", "1d")
            
        Returns:
            True se pode chamar, False se bloqueado
        """
        if not self.enabled:
            return True
        
        self._check_day_rollover()
        
        # 1. Verifica limite diário
        if self.state.claude_calls >= self.claude_max:
            self.log.warning(
                f"{self.log_prefix}[BLOCKED] Claude: DAILY_LIMIT atingido "
                f"({self.state.claude_calls}/{self.claude_max}) | "
                f"trigger={reason} symbol={symbol} tf={timeframe}"
            )
            return False
        
        # 2. Verifica cooldown
        if not self._is_cooldown_ok(self.state.claude_last_call, self.claude_cooldown_min):
            remaining = self._minutes_until_cooldown_ok(self.state.claude_last_call, self.claude_cooldown_min)
            self.log.info(
                f"{self.log_prefix}[BLOCKED] Claude: COOLDOWN ({remaining:.1f}min restantes) | "
                f"trigger={reason} symbol={symbol} tf={timeframe}"
            )
            return False
        
        # 3. Verifica se símbolo está na lista permitida
        symbol_clean = symbol.replace("USDC", "").replace("USDT", "").replace("USD", "")
        if symbol_clean not in self.swing_symbols:
            if self.debug:
                self.log.debug(f"{self.log_prefix} Claude: símbolo {symbol} não está na lista swing")
            return False
        
        if self.debug:
            self.log.debug(
                f"{self.log_prefix} Claude: PERMITIDO | "
                f"calls={self.state.claude_calls}/{self.claude_max} | "
                f"trigger={reason} symbol={symbol}"
            )
        
        return True
    
    def register_claude_call(self, reason: str, symbol: str, timeframe: str):
        """Registra uma chamada de Claude"""
        self._check_day_rollover()
        
        now = datetime.now(timezone.utc)
        self.state.claude_calls += 1
        self.state.claude_last_call = now
        self.state.claude_history.append(AICallRecord(
            timestamp=now,
            reason=reason,
            symbol=symbol,
            timeframe=timeframe
        ))
        
        self.log.info(
            f"{self.log_prefix} Claude calls today: {self.state.claude_calls}/{self.claude_max}, "
            f"last_call={now.strftime('%H:%M')}, reason={reason}, symbol={symbol}"
        )
        
        self._check_warn_threshold("Claude", self.state.claude_calls, self.claude_max)
    
    # ==================== OPENAI (SCALP) ====================
    
    def can_call_openai(self, reason: str, symbol: str, timeframe: str) -> bool:
        """
        Verifica se pode chamar OpenAI (IA Scalp)
        
        Args:
            reason: Motivo da chamada (ex: "PULLBACK_EMA", "RANGE_BREAKOUT")
            symbol: Símbolo
            timeframe: Timeframe
            
        Returns:
            True se pode chamar, False se bloqueado
        """
        if not self.enabled:
            return True
        
        self._check_day_rollover()
        
        # 1. Verifica limite diário
        if self.state.openai_calls >= self.openai_max:
            self.log.warning(
                f"{self.log_prefix}[BLOCKED] OpenAI: DAILY_LIMIT atingido "
                f"({self.state.openai_calls}/{self.openai_max}) | "
                f"trigger={reason} symbol={symbol} tf={timeframe}"
            )
            return False
        
        # 2. Verifica cooldown
        if not self._is_cooldown_ok(self.state.openai_last_call, self.openai_cooldown_min):
            remaining = self._minutes_until_cooldown_ok(self.state.openai_last_call, self.openai_cooldown_min)
            if self.debug:
                self.log.debug(
                    f"{self.log_prefix}[BLOCKED] OpenAI: COOLDOWN ({remaining:.1f}min) | "
                    f"trigger={reason} symbol={symbol}"
                )
            return False
        
        # 3. Verifica se símbolo está na lista permitida
        symbol_clean = symbol.replace("USDC", "").replace("USDT", "").replace("USD", "")
        if symbol_clean not in self.scalp_symbols:
            if self.debug:
                self.log.debug(f"{self.log_prefix} OpenAI: símbolo {symbol} não está na lista scalp")
            return False
        
        if self.debug:
            self.log.debug(
                f"{self.log_prefix} OpenAI: PERMITIDO | "
                f"calls={self.state.openai_calls}/{self.openai_max} | "
                f"trigger={reason} symbol={symbol}"
            )
        
        return True
    
    def register_openai_call(self, reason: str, symbol: str, timeframe: str):
        """Registra uma chamada de OpenAI"""
        self._check_day_rollover()
        
        now = datetime.now(timezone.utc)
        self.state.openai_calls += 1
        self.state.openai_last_call = now
        self.state.openai_history.append(AICallRecord(
            timestamp=now,
            reason=reason,
            symbol=symbol,
            timeframe=timeframe
        ))
        
        self.log.info(
            f"{self.log_prefix} OpenAI calls today: {self.state.openai_calls}/{self.openai_max}, "
            f"last_call={now.strftime('%H:%M')}, reason={reason}, symbol={symbol}"
        )
        
        self._check_warn_threshold("OpenAI", self.state.openai_calls, self.openai_max)
    
    # ==================== STATUS ====================
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status atual do orçamento"""
        self._check_day_rollover()
        
        claude_cooldown_ok = self._is_cooldown_ok(self.state.claude_last_call, self.claude_cooldown_min)
        openai_cooldown_ok = self._is_cooldown_ok(self.state.openai_last_call, self.openai_cooldown_min)
        
        return {
            "date": self.state.date,
            "enabled": self.enabled,
            "claude": {
                "calls_today": self.state.claude_calls,
                "max_calls": self.claude_max,
                "remaining": max(0, self.claude_max - self.state.claude_calls),
                "last_call": self.state.claude_last_call.isoformat() if self.state.claude_last_call else None,
                "cooldown_ok": claude_cooldown_ok,
                "cooldown_minutes": self.claude_cooldown_min
            },
            "openai": {
                "calls_today": self.state.openai_calls,
                "max_calls": self.openai_max,
                "remaining": max(0, self.openai_max - self.state.openai_calls),
                "last_call": self.state.openai_last_call.isoformat() if self.state.openai_last_call else None,
                "cooldown_ok": openai_cooldown_ok,
                "cooldown_minutes": self.openai_cooldown_min
            }
        }
    
    def get_status_summary(self) -> str:
        """Retorna resumo do status para logs"""
        self._check_day_rollover()
        
        claude_cd = "✅" if self._is_cooldown_ok(self.state.claude_last_call, self.claude_cooldown_min) else "⏳"
        openai_cd = "✅" if self._is_cooldown_ok(self.state.openai_last_call, self.openai_cooldown_min) else "⏳"
        
        return (
            f"{self.log_prefix} Claude: {self.state.claude_calls}/{self.claude_max} {claude_cd} | "
            f"OpenAI: {self.state.openai_calls}/{self.openai_max} {openai_cd}"
        )
