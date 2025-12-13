# Fix PnL Baselines - InspetorPro

Este script corrige os baselines de PnL para que os períodos 7D, 30D e ALL TIME mostrem valores corretos.

## 🎯 Problema

Atualmente, o dashboard mostra:
- **24H PnL**: +3.27% ✅ (correto)
- **7D PnL**: +3.27% ❌ (errado - igual ao 24H)
- **30D PnL**: +3.27% ❌ (errado - igual ao 24H)

**Causa:** O bot só tem histórico de equity das últimas 24-48h. Os baselines de 7D e 30D foram criados com o mesmo valor inicial que 24H.

## 🔧 Solução

Use este script para setar os baselines corretos com base nos valores históricos reais da sua conta.

## 📋 Pré-requisitos

```bash
pip install requests
```

## 🚀 Uso

### 1. Ver PnL Atual

```bash
python fix_pnl_baselines.py --show-current
```

**Output:**
```
📈 PnL Atual:
  Current Equity: $47.26
  ALL TIME: +372.47% ($37.26)
  24H: +3.27% ($1.50)
  7D: +3.27% ($1.50)  ← ERRADO
  30D: +3.27% ($1.50)  ← ERRADO
```

### 2. Corrigir ALL TIME Baseline

Se você começou com $10 em 01/11/2024:

```bash
python fix_pnl_baselines.py --all-time 10.0 --all-time-date 2024-11-01
```

### 3. Corrigir WEEK Baseline

Se você tinha $42 há 7 dias (06/12/2024):

```bash
python fix_pnl_baselines.py --week 42.0 --week-date 2024-12-06
```

### 4. Corrigir MONTH Baseline

Se você tinha $35 há 30 dias (01/12/2024):

```bash
python fix_pnl_baselines.py --month 35.0 --month-date 2024-12-01
```

### 5. Corrigir Todos de Uma Vez

```bash
python fix_pnl_baselines.py \
    --all-time 10.0 --all-time-date 2024-11-01 \
    --week 42.0 --week-date 2024-12-06 \
    --month 35.0 --month-date 2024-12-01
```

## 📊 Resultado Esperado

Após executar o script, o dashboard mostrará:

```
📈 PnL Atual:
  Current Equity: $47.26
  ALL TIME: +372.47% ($37.26)  ✅ Correto
  24H: +3.27% ($1.50)          ✅ Correto
  7D: +12.5% ($5.26)           ✅ Correto (agora diferente!)
  30D: +35.0% ($12.26)         ✅ Correto (agora diferente!)
```

## 🤔 Como Descobrir os Valores Históricos?

### Opção A: Você tem registros

Se você anotou ou tem prints da conta em datas específicas, use esses valores.

### Opção B: Estimativa baseada em trades

1. Veja o histórico de trades no dashboard
2. Some os PnLs realizados desde uma data específica
3. Subtraia do equity atual

**Exemplo:**
- Equity atual: $47.26
- Soma de PnLs dos últimos 7 dias: +$5.26
- Equity há 7 dias: $47.26 - $5.26 = **$42.00**

### Opção C: Usar equity atual como baseline

Se você não tem dados históricos, pode usar o equity atual como baseline e começar a contar daqui pra frente:

```bash
# Usar equity atual ($47.26) como baseline de hoje
python fix_pnl_baselines.py \
    --all-time 47.26 --all-time-date 2024-12-13 \
    --week 47.26 --week-date 2024-12-13 \
    --month 47.26 --month-date 2024-12-13
```

**Resultado:** Todos os PnLs começarão em 0% e crescerão daqui pra frente.

## 🔐 Configuração

O script usa as seguintes variáveis de ambiente (ou valores padrão):

```bash
export BOT_API_URL="https://inspetorpro.up.railway.app"
export BOT_API_KEY="inspetorpro159"
```

## ⚠️ Importante

> **ATENÇÃO:** Setar o baseline errado resultará em cálculos de PnL incorretos permanentemente!
> 
> Certifique-se de que os valores estão corretos antes de executar.

## 🧪 Testar Antes de Aplicar

1. Execute `--show-current` para ver os valores atuais
2. Calcule mentalmente o PnL esperado
3. Execute o script
4. Execute `--show-current` novamente para verificar

**Exemplo:**
```bash
# Antes
python fix_pnl_baselines.py --show-current
# ALL TIME: +372.47% ($37.26)

# Aplicar
python fix_pnl_baselines.py --all-time 10.0 --all-time-date 2024-11-01

# Verificar
python fix_pnl_baselines.py --show-current
# ALL TIME: +372.60% ($37.26)  ← Deve estar próximo do esperado
```

## 📝 Logs

O script mostra logs detalhados:

```
🔧 InspetorPro - Fix PnL Baselines
==================================================
📊 Setando baseline ALL_TIME: $10.0 @ 2024-11-01
✅ Baseline all_time atualizado com sucesso!
📊 Setando baseline WEEK: $42.0 @ 2024-12-06
✅ Baseline week atualizado com sucesso!

==================================================
✅ 2/2 baselines atualizados com sucesso!

🔄 Aguarde alguns segundos e verifique o dashboard:
   https://inspetorpro.up.railway.app

💡 Dica: Use --show-current para ver os novos valores de PnL
```

## 🆘 Troubleshooting

### Erro: "Bot API error: 401"
- Verifique se `BOT_API_KEY` está correto
- Confirme que a API está rodando

### Erro: "Connection refused"
- Verifique se `BOT_API_URL` está correto
- Confirme que o Railway está online

### PnL ainda aparece errado
- Aguarde 10-30 segundos (cache do dashboard)
- Recarregue a página (Ctrl+F5)
- Verifique se os valores foram realmente aplicados com `--show-current`

## 📚 Mais Informações

Para detalhes técnicos sobre como os baselines funcionam, veja:
- `bot/telemetry_store.py` - Método `get_pnl_summary()`
- `bot/dashboard_api.py` - Endpoint `/api/set-initial-equity`

---

**Criado por:** Antigravity AI  
**Data:** 2024-12-13  
**Versão:** 1.0
