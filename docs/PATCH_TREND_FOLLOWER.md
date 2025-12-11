# 🏄 PATCH TREND FOLLOWER - Documentação

**Data**: 2024-12-11  
**Versão**: Claude Trend Refactor v1.0  
**Autor**: Claude (via Antigravity)

---

## 📋 Resumo das Mudanças

Este patch transforma o bot em um **surfista de tendência** que:
- Opera majoritariamente A FAVOR da tendência principal
- Bloqueia trades contra-tendência
- Usa pyramiding controlado para aumentar posições vencedoras
- Implementa trailing stop inteligente
- Ajusta filtros para serem contexto-sensíveis

---

## 📁 Arquivos Modificados

### 1. `bot/phase3/trend_guard.py` (NOVO)
Módulo que implementa regras DURAS de alinhamento com tendência.

**Funcionalidades:**
- Bloqueia open_short quando trend_bias = "long"
- Bloqueia open_long quando trend_bias = "short"
- Em neutral, exige confidence mais alta
- Configurável por modo (Conservador/Balanceado/Agressivo)

**Uso:**
```python
from bot.phase3 import TrendGuard

trend_guard = TrendGuard(mode_manager=self.mode_manager)
result = trend_guard.evaluate(decision, regime_info, confidence)

if not result.allowed:
    print(f"BLOQUEADO: {result.reason}")
```

---

### 2. `bot/phase3/market_regime.py` (MODIFICADO)
Adicionada análise de tendência por EMAs como alternativa mais tolerante.

**Mudanças:**
- Novo método `_analyze_trend_by_ema()` usando EMA50/EMA200
- Fallback `_analyze_trend_by_short_ema()` com EMA21/EMA50
- Combina análise EMA com swing analysis original
- Prioriza EMA por ser mais estável

**Critérios de tendência:**
```
TREND_BULL: Preço > EMA200 E EMA50 > EMA200
TREND_BEAR: Preço < EMA200 E EMA50 < EMA200
NEUTRAL: Caso contrário
```

---

### 3. `bot/phase2/decision_parser.py` (MODIFICADO)
Melhorias no parse de respostas da IA para evitar confidence = 0.0.

**Mudanças:**
- Default confidence = 0.70 (era 0.0)
- Limpeza mais agressiva de markdown no JSON
- Extrai trend_bias da resposta
- Tratamento de confidence como string ("75%" → 0.75)
- Warning quando confidence muito baixo

---

### 4. `bot/ai_decision.py` (MODIFICADO)
Prompt reformulado com foco em trend following.

**Mudanças:**
- Nova filosofia: "SURFISTA DE TENDÊNCIA"
- Passa trend_bias explicitamente no contexto
- Formato JSON mais rígido com exemplos claros
- Regras detalhadas para o campo confidence
- Lembrete para alinhar side com trend_bias

---

### 5. `bot/phase2/quality_gate.py` (MODIFICADO)
Integração com TrendGuard e filtros contexto-sensíveis.

**Mudanças:**
- CRITÉRIO 0.5: Verificação TrendGuard antes de outros filtros
- ChopFilter mais tolerante quando há tendência clara
- Scalp só bloqueado em chop SE não houver tendência
- Logs melhorados com trend_bias

---

### 6. `bot/position_manager.py` (MODIFICADO)
Pyramiding controlado e trailing stop avançado.

**Novos métodos:**
- `check_pyramid_opportunity()` - Verifica se pode fazer add
- `execute_pyramid_add()` - Executa o add atualizando preço médio
- `calculate_trailing_stop()` - Trailing por EMA, ATR ou Structure

**Regras de Pyramiding:**
- Posição deve estar em lucro (min 0.3-1% dependendo do modo)
- trend_bias deve estar alinhado
- Regime deve ser de tendência
- Limite de adds: 1-3 dependendo do modo

---

## ⚙️ Configuração

### Parâmetros do TrendGuard por Modo:

| Modo | Permite Neutral | Min Confidence Neutral |
|------|-----------------|------------------------|
| CONSERVADOR | ❌ Não | 0.90 |
| BALANCEADO | ✅ Sim | 0.85 |
| AGRESSIVO | ✅ Sim | 0.78 |

### Parâmetros de Pyramiding por Modo:

| Modo | Max Adds | Min PnL | Size Add |
|------|----------|---------|----------|
| CONSERVADOR | 1 | 1.0% | 30% |
| BALANCEADO | 2 | 0.5% | 50% |
| AGRESSIVO | 3 | 0.3% | 50% |

---

## 🧪 Como Testar

1. **Verificar sintaxe:**
```bash
python3 -m py_compile bot/phase3/trend_guard.py
python3 -m py_compile bot/phase3/market_regime.py
python3 -m py_compile bot/phase2/decision_parser.py
python3 -m py_compile bot/phase2/quality_gate.py
python3 -m py_compile bot/position_manager.py
python3 -m py_compile bot/ai_decision.py
```

2. **Rodar em paper trading:**
- Observar logs de `[TREND GUARD]`
- Verificar se trades contra-tendência são bloqueados
- Checar se confidence está vindo corretamente (não 0.0)

3. **Logs esperados:**
```
[TREND GUARD] ✅ BTCUSDT aprovado: trend_bias=long, regime=TREND_BULL
[TREND GUARD] 🚫 ETHUSDT BLOQUEADO: open_short contra tendência LONG
[QUALITY GATE] Chop tolerado em BTCUSDT por tendência long
[PARSER] ✅ Open decision parsed: BTCUSDT long swing conf=0.78 trend_bias=long
[PYRAMID] ✅ BTCUSDT: Oportunidade de add! PnL=1.5%, trend_bias=long
```

---

## 🔄 Rollback

Se precisar reverter, os arquivos originais podem ser restaurados do git:
```bash
git checkout -- bot/phase3/market_regime.py
git checkout -- bot/phase2/decision_parser.py
git checkout -- bot/phase2/quality_gate.py
git checkout -- bot/position_manager.py
git checkout -- bot/ai_decision.py
rm bot/phase3/trend_guard.py
```

---

## 📝 Próximos Passos (TODO)

1. [ ] Implementar proteção swing vs scalp (evitar que scalp destrua swing)
2. [ ] Adicionar métricas de performance por tendência
3. [ ] Dashboard de visualização de trend_bias em tempo real
4. [ ] Backtesting com as novas regras

---

## 🚀 Conclusão

O bot agora está configurado para ser um **trend follower consistente**:
- ✅ Opera a favor da tendência
- ✅ Bloqueia trades contra-tendência
- ✅ Permite pyramiding quando alinhado
- ✅ Trailing stop para proteger lucros
- ✅ Filtros menos agressivos em tendência clara
- ✅ Confidence com defaults seguros
