from enum import Enum

class TradeState(Enum):
    """Estado atual do trade na máquina de estados de gestão"""
    INIT = "INIT"  # Recém aberto, nenhuma parcial
    SCALP_ACTIVE = "SCALP_ACTIVE"  # Já fez parcial/BE, gerenciando como scalp
    PROMOTED_TO_SWING = "PROMOTED_TO_SWING"  # Promovido a runner, trailing estrutural
    CLOSED = "CLOSED"  # Encerrado

class ManagementProfile(Enum):
    """Perfil de gestão do trade"""
    SCALP_ONLY = "SCALP_ONLY"  # Morre como scalp
    SCALP_CAN_PROMOTE = "SCALP_CAN_PROMOTE"  # Tenta virar swing
    SWING = "SWING"  # Nascido para swing
