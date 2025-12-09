"""
Phase 6 - Global Risk Guardrails & Circuit Breaker
Sistema avançado de proteção de banca com limites duros e cooldown
"""
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RiskState(Enum):
    """Estados do circuit breaker"""
    RUNNING = "RUNNING"
    COOLDOWN = "COOLDOWN"
    HALTED_DAILY = "HALTED_DAILY"
    HALTED_WEEKLY = "HALTED_WEEKLY"
    HALTED_DRAWDOWN = "HALTED_DRAWDOWN"


class GlobalRiskManager:
    """
    Gerenciador de risco global com circuit breaker
    
    Responsável por:
    - Monitorar perdas diárias, semanais e drawdown
    - Ativar circuit breaker quando limites são atingidos
    - Gerenciar cooldown após losing streaks
    - Integrar com modos de trading (Fase 5)
    - Persistir estado para sobreviver restart
    """
    
    STATE_FILE = "data/risk_state.json"
    
    # Configurações de risco
    RISK_LIMITS = {
        'daily_loss_limit_pct': 3.0,      # % da equity
        'weekly_loss_limit_pct': 8.0,     # % da equity
        'max_drawdown_pct': 25.0,         # % desde equity_peak
        'max_losing_streak': 4,           # trades perdedores seguidos
        'cooldown_minutes': 60,           # tempo de cooldown
        'auto_close_on_halt': True,       # fechar tudo quando HALTED
        'auto_downgrade_mode_on_risk': True  # ajustar modo automaticamente
    }
    
    def __init__(self, mode_manager=None, logger_instance=None):
        """
        Inicializa Global Risk Manager
        
        Args:
            mode_manager: Trading Mode Manager (Fase 5)
            logger_instance: Logger opcional
        """
        self.logger = logger_instance or logger
        self.mode_manager = mode_manager
        
        # Estado de risco
        self.current_mode = RiskState.RUNNING
        self.equity_peak = 0.0
        self.equity_start_day = 0.0
        self.equity_start_week = 0.0
        self.daily_pnl = 0.0
        self.daily_pnl_pct = 0.0
        self.weekly_pnl = 0.0
        self.weekly_pnl_pct = 0.0
        self.drawdown_pct = 0.0
        self.losing_streak = 0
        self.cooldown_until = 0
        self.last_day = datetime.utcnow().date()
        self.last_week = datetime.utcnow().isocalendar()[1]
        
        # Flags de notificação (para não spammar Telegram)
        self.notified_states = set()
        
        # Carrega estado
        self._load_state()
        
        self.logger.info(
            f"[RISK] Global Risk Manager iniciado | "
            f"State: {self.current_mode.value} | "
            f"Daily Limit: {self.RISK_LIMITS['daily_loss_limit_pct']}% | "
            f"Weekly Limit: {self.RISK_LIMITS['weekly_loss_limit_pct']}% | "
            f"Max DD: {self.RISK_LIMITS['max_drawdown_pct']}%"
        )
    
    def update_equity(self, current_equity: float, trade_pnl: Optional[float] = None,
                     trade_was_loss: Optional[bool] = None) -> Dict[str, Any]:
        """
        Atualiza estado de risco baseado em equity atual
        
        Args:
            current_equity: Equity atual em USD
            trade_pnl: PnL do último trade (se houver)
            trade_was_loss: Se o último trade foi perda
            
        Returns:
            Dict com estado atualizado e ações necessárias
        """
        try:
            # Reseta contadores diários/semanais se necessário
            self._check_day_week_reset()
            
            # Primeira vez? Inicializa
            if self.equity_peak == 0:
                self.equity_peak = current_equity
                self.equity_start_day = current_equity
                self.equity_start_week = current_equity
                self._save_state()
                return {'state': self.current_mode.value, 'actions': []}
            
            # Atualiza equity peak
            if current_equity > self.equity_peak:
                self.equity_peak = current_equity
                self.drawdown_pct = 0.0
                self.logger.debug(f"[RISK] Novo equity peak: ${current_equity:.2f}")
            else:
                # Calcula drawdown
                self.drawdown_pct = ((current_equity - self.equity_peak) / self.equity_peak) * 100
            
            # Atualiza PnL diário e semanal
            self.daily_pnl = current_equity - self.equity_start_day
            self.daily_pnl_pct = (self.daily_pnl / self.equity_start_day) * 100 if self.equity_start_day > 0 else 0
            
            self.weekly_pnl = current_equity - self.equity_start_week
            self.weekly_pnl_pct = (self.weekly_pnl / self.equity_start_week) * 100 if self.equity_start_week > 0 else 0
            
            # Atualiza losing streak
            if trade_was_loss is not None:
                if trade_was_loss:
                    self.losing_streak += 1
                else:
                    self.losing_streak = 0
            
            # Verifica limites e atualiza estado
            actions = self._check_limits_and_update_state()
            
            # Salva estado
            self._save_state()
            
            return {
                'state': self.current_mode.value,
                'actions': actions,
                'daily_pnl_pct': self.daily_pnl_pct,
                'weekly_pnl_pct': self.weekly_pnl_pct,
                'drawdown_pct': self.drawdown_pct,
                'losing_streak': self.losing_streak
            }
            
        except Exception as e:
            self.logger.error(f"[RISK][ERROR] Erro ao atualizar equity: {e}", exc_info=True)
            # Fallback seguro
            self.current_mode = RiskState.COOLDOWN
            self.cooldown_until = time.time() + (self.RISK_LIMITS['cooldown_minutes'] * 60)
            return {'state': 'COOLDOWN', 'actions': ['BLOCK_NEW_ENTRIES']}
    
    def can_open_new_trade(self) -> Tuple[bool, str]:
        """
        Verifica se pode abrir novo trade
        
        Returns:
            (pode_abrir, razão)
        """
        # Verifica cooldown
        if self.current_mode == RiskState.COOLDOWN:
            if time.time() < self.cooldown_until:
                cooldown_end = datetime.fromtimestamp(self.cooldown_until).strftime('%H:%M')
                return False, f"COOLDOWN ativo até {cooldown_end}"
            else:
                # Cooldown expirou, volta para RUNNING
                self._exit_cooldown()
        
        # Verifica estados HALTED
        if self.current_mode == RiskState.HALTED_DAILY:
            return False, f"Circuit Breaker DIÁRIO ativado (perda {self.daily_pnl_pct:.2f}%)"
        
        if self.current_mode == RiskState.HALTED_WEEKLY:
            return False, f"Circuit Breaker SEMANAL ativado (perda {self.weekly_pnl_pct:.2f}%)"
        
        if self.current_mode == RiskState.HALTED_DRAWDOWN:
            return False, f"Circuit Breaker DRAWDOWN ativado (DD {self.drawdown_pct:.2f}%)"
        
        # RUNNING - pode operar
        return True, "OK"
    
    def force_cooldown(self, minutes: Optional[int] = None, source: str = "manual") -> bool:
        """
        Força entrada em cooldown
        
        Args:
            minutes: Duração do cooldown (None = padrão)
            source: Origem do comando
            
        Returns:
            True se bem-sucedido
        """
        try:
            duration = minutes or self.RISK_LIMITS['cooldown_minutes']
            self.current_mode = RiskState.COOLDOWN
            self.cooldown_until = time.time() + (duration * 60)
            
            cooldown_end = datetime.fromtimestamp(self.cooldown_until).strftime('%H:%M')
            self.logger.info(
                f"[RISK] Cooldown {source} ativado por {duration} min até {cooldown_end}"
            )
            
            self._save_state()
            return True
            
        except Exception as e:
            self.logger.error(f"[RISK] Erro ao ativar cooldown: {e}")
            return False
    
    def reset_daily_limits(self, source: str = "manual") -> bool:
        """
        Reseta limites diários (use com cuidado!)
        
        Args:
            source: Origem do reset
            
        Returns:
            True se bem-sucedido
        """
        try:
            self.daily_pnl = 0.0
            self.daily_pnl_pct = 0.0
            self.equity_start_day = self.equity_peak  # Assume que está no peak
            
            # Se estava HALTED_DAILY, volta para RUNNING
            if self.current_mode == RiskState.HALTED_DAILY:
                self.current_mode = RiskState.RUNNING
                self.logger.info(f"[RISK] Estado mudou de HALTED_DAILY para RUNNING (reset {source})")
            
            self.logger.warning(f"[RISK] Reset {source} de métricas diárias executado")
            self._save_state()
            return True
            
        except Exception as e:
            self.logger.error(f"[RISK] Erro ao resetar limites diários: {e}")
            return False
    
    def reset_weekly_limits(self, source: str = "manual") -> bool:
        """
        Reseta limites semanais (use com cuidado!)
        
        Args:
            source: Origem do reset
            
        Returns:
            True se bem-sucedido
        """
        try:
            self.weekly_pnl = 0.0
            self.weekly_pnl_pct = 0.0
            self.equity_start_week = self.equity_peak
            
            # Se estava HALTED_WEEKLY, volta para RUNNING
            if self.current_mode == RiskState.HALTED_WEEKLY:
                self.current_mode = RiskState.RUNNING
                self.logger.info(f"[RISK] Estado mudou de HALTED_WEEKLY para RUNNING (reset {source})")
            
            self.logger.warning(f"[RISK] Reset {source} de métricas semanais executado")
            self._save_state()
            return True
            
        except Exception as e:
            self.logger.error(f"[RISK] Erro ao resetar limites semanais: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Retorna status completo de risco
        
        Returns:
            Dict com todas métricas
        """
        return {
            'state': self.current_mode.value,
            'equity_peak': self.equity_peak,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_pct': self.daily_pnl_pct,
            'weekly_pnl': self.weekly_pnl,
            'weekly_pnl_pct': self.weekly_pnl_pct,
            'drawdown_pct': self.drawdown_pct,
            'losing_streak': self.losing_streak,
            'cooldown_until': self.cooldown_until,
            'limits': self.RISK_LIMITS
        }
    
    def _check_limits_and_update_state(self) -> list:
        """
        Verifica limites e atualiza estado
        
        Returns:
            Lista de ações necessárias
        """
        actions = []
        old_state = self.current_mode
        
        # Verifica drawdown
        if self.drawdown_pct <= -self.RISK_LIMITS['max_drawdown_pct']:
            self.current_mode = RiskState.HALTED_DRAWDOWN
            if old_state != RiskState.HALTED_DRAWDOWN:
                self.logger.error(
                    f"[RISK] 🔴 Circuit Breaker DRAWDOWN ativado: {self.drawdown_pct:.2f}% "
                    f"(limite: -{self.RISK_LIMITS['max_drawdown_pct']}%)"
                )
                actions.append('HALT_DRAWDOWN')
                if self.RISK_LIMITS['auto_close_on_halt']:
                    actions.append('CLOSE_ALL_POSITIONS')
        
        # Verifica perda semanal
        elif self.weekly_pnl_pct <= -self.RISK_LIMITS['weekly_loss_limit_pct']:
            self.current_mode = RiskState.HALTED_WEEKLY
            if old_state != RiskState.HALTED_WEEKLY:
                self.logger.error(
                    f"[RISK] 🔴 Circuit Breaker SEMANAL ativado: {self.weekly_pnl_pct:.2f}% "
                    f"(limite: -{self.RISK_LIMITS['weekly_loss_limit_pct']}%)"
                )
                actions.append('HALT_WEEKLY')
                if self.RISK_LIMITS['auto_close_on_halt']:
                    actions.append('CLOSE_ALL_POSITIONS')
        
        # Verifica perda diária
        elif self.daily_pnl_pct <= -self.RISK_LIMITS['daily_loss_limit_pct']:
            self.current_mode = RiskState.HALTED_DAILY
            if old_state != RiskState.HALTED_DAILY:
                self.logger.error(
                    f"[RISK] 🔴 Circuit Breaker DIÁRIO ativado: {self.daily_pnl_pct:.2f}% "
                    f"(limite: -{self.RISK_LIMITS['daily_loss_limit_pct']}%)"
                )
                actions.append('HALT_DAILY')
                if self.RISK_LIMITS['auto_close_on_halt']:
                    actions.append('CLOSE_ALL_POSITIONS')
        
        # Verifica losing streak (se não estiver HALTED)
        elif self.losing_streak >= self.RISK_LIMITS['max_losing_streak']:
            if self.current_mode != RiskState.COOLDOWN:
                self.current_mode = RiskState.COOLDOWN
                self.cooldown_until = time.time() + (self.RISK_LIMITS['cooldown_minutes'] * 60)
                cooldown_end = datetime.fromtimestamp(self.cooldown_until).strftime('%H:%M')
                self.logger.warning(
                    f"[RISK] ⚠️ Cooldown ativado: {self.losing_streak} trades perdedores seguidos. "
                    f"Sem novas entradas até {cooldown_end}"
                )
                actions.append('COOLDOWN')
        
        # Auto-ajuste de modo (se habilitado)
        if old_state != self.current_mode and self.RISK_LIMITS['auto_downgrade_mode_on_risk']:
            mode_action = self._auto_adjust_mode()
            if mode_action:
                actions.append(mode_action)
        
        return actions
    
    def _auto_adjust_mode(self) -> Optional[str]:
        """
        Ajusta modo automaticamente baseado no estado de risco
        
        Returns:
            Ação executada ou None
        """
        if not self.mode_manager:
            return None
        
        try:
            from bot.phase5 import TradingMode
            
            current_trading_mode = self.mode_manager.get_current_mode()
            
            # HALTED -> Conservador
            if self.current_mode in [RiskState.HALTED_DAILY, RiskState.HALTED_WEEKLY, RiskState.HALTED_DRAWDOWN]:
                if current_trading_mode != TradingMode.CONSERVADOR:
                    self.mode_manager.set_mode(TradingMode.CONSERVADOR, source="risk_auto_downgrade")
                    self.logger.warning(
                        f"[MODE] Auto-ajuste: {current_trading_mode.value} -> CONSERVADOR "
                        f"(circuit breaker ativado)"
                    )
                    return 'MODE_DOWNGRADED_TO_CONSERVADOR'
            
            # COOLDOWN -> Balanceado (se estava Agressivo)
            elif self.current_mode == RiskState.COOLDOWN:
                if current_trading_mode == TradingMode.AGRESSIVO:
                    self.mode_manager.set_mode(TradingMode.BALANCEADO, source="risk_cooldown")
                    self.logger.warning(
                        f"[MODE] Auto-ajuste: AGRESSIVO -> BALANCEADO (cooldown ativado)"
                    )
                    return 'MODE_DOWNGRADED_TO_BALANCEADO'
            
        except Exception as e:
            self.logger.error(f"[RISK] Erro ao ajustar modo: {e}")
        
        return None
    
    def _exit_cooldown(self):
        """Sai do cooldown e volta para RUNNING"""
        if self.current_mode == RiskState.COOLDOWN:
            self.current_mode = RiskState.RUNNING
            self.logger.info("[RISK] ✅ Cooldown encerrado. Voltando a operar.")
            self._save_state()
    
    def _check_day_week_reset(self):
        """Verifica e reseta contadores diários/semanais"""
        now = datetime.utcnow()
        current_day = now.date()
        current_week = now.isocalendar()[1]
        
        # Novo dia?
        if current_day != self.last_day:
            self.logger.info(f"[RISK] Novo dia detectado. Resetando métricas diárias.")
            self.daily_pnl = 0.0
            self.daily_pnl_pct = 0.0
            self.equity_start_day = self.equity_peak
            self.losing_streak = 0
            
            # Se estava HALTED_DAILY, volta para RUNNING
            if self.current_mode == RiskState.HALTED_DAILY:
                self.current_mode = RiskState.RUNNING
                self.logger.info("[RISK] Estado mudou de HALTED_DAILY para RUNNING (novo dia)")
            
            self.last_day = current_day
        
        # Nova semana?
        if current_week != self.last_week:
            self.logger.info(f"[RISK] Nova semana detectada. Resetando métricas semanais.")
            self.weekly_pnl = 0.0
            self.weekly_pnl_pct = 0.0
            self.equity_start_week = self.equity_peak
            
            # Se estava HALTED_WEEKLY, volta para RUNNING
            if self.current_mode == RiskState.HALTED_WEEKLY:
                self.current_mode = RiskState.RUNNING
                self.logger.info("[RISK] Estado mudou de HALTED_WEEKLY para RUNNING (nova semana)")
            
            self.last_week = current_week
    
    def _load_state(self):
        """Carrega estado persistido"""
        try:
            state_file = Path(self.STATE_FILE)
            
            if not state_file.exists():
                self.logger.info("[RISK] Estado de risco inexistente. Iniciando novo state em RUNNING.")
                self._save_state()
                return
            
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            self.current_mode = RiskState[data.get('current_mode', 'RUNNING')]
            self.equity_peak = data.get('equity_peak', 0.0)
            self.equity_start_day = data.get('equity_start_day', 0.0)
            self.equity_start_week = data.get('equity_start_week', 0.0)
            self.daily_pnl = data.get('daily_pnl', 0.0)
            self.daily_pnl_pct = data.get('daily_pnl_pct', 0.0)
            self.weekly_pnl = data.get('weekly_pnl', 0.0)
            self.weekly_pnl_pct = data.get('weekly_pnl_pct', 0.0)
            self.drawdown_pct = data.get('drawdown_pct', 0.0)
            self.losing_streak = data.get('losing_streak', 0)
            self.cooldown_until = data.get('cooldown_until', 0)
            self.last_day = datetime.fromisoformat(data.get('last_day', datetime.utcnow().date().isoformat())).date()
            self.last_week = data.get('last_week', datetime.utcnow().isocalendar()[1])
            
            self.logger.info(f"[RISK] Estado de risco carregado: {data}")
            
        except Exception as e:
            self.logger.warning(
                f"[RISK] Erro ao carregar estado: {e}. "
                f"Iniciando novo state em RUNNING."
            )
            self.current_mode = RiskState.RUNNING
    
    def _save_state(self):
        """Salva estado no arquivo"""
        try:
            state_file = Path(self.STATE_FILE)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'current_mode': self.current_mode.value,
                'equity_peak': self.equity_peak,
                'equity_start_day': self.equity_start_day,
                'equity_start_week': self.equity_start_week,
                'daily_pnl': self.daily_pnl,
                'daily_pnl_pct': self.daily_pnl_pct,
                'weekly_pnl': self.weekly_pnl,
                'weekly_pnl_pct': self.weekly_pnl_pct,
                'drawdown_pct': self.drawdown_pct,
                'losing_streak': self.losing_streak,
                'cooldown_until': self.cooldown_until,
                'last_day': self.last_day.isoformat(),
                'last_week': self.last_week
            }
            
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"[RISK] Estado salvo: {self.current_mode.value}")
            
        except Exception as e:
            self.logger.error(f"[RISK] Erro ao salvar estado: {e}", exc_info=True)
