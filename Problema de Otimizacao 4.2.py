import numpy as np
from scipy.optimize import fsolve
import matplotlib.pyplot as plt

# =============================================
# PARÂMETROS DO SISTEMA
# =============================================
A = 185  # Área do reservatório (m²)
h_min, h_max = 2, 7  # Limites do nível (m)
h = 4.0  # Nível inicial (m)
f = 0.02
d = 0.3
L_PR = 2500
L_RF = 5000
eta = 0.65
rho = 1000
g = 9.81

# Constantes otimizadas
d5_pi2_g = (d**5) * (np.pi**2) * g
const_perdas = 32 * f / d5_pi2_g
power_const = rho * g / (eta * 3600 * 1000)  # Conversão para kWh

# Tarifário (€/kWh) - Indexado por hora (0-23)
tarifario = np.array([
    0.0593, 0.0593, 0.0593, 0.0593, 0.0593, 0.0593,  # 0h-5h (melhores tarifas)
    0.0778, 0.0778, 0.0851, 0.0851, 0.0923, 0.0923,  # 6h-11h
    0.0968, 0.0968, 0.10094, 0.10094, 0.10132, 0.10132,  # 12h-17h
    0.10230, 0.10230, 0.10189, 0.10189, 0.10132, 0.10132  # 18h-23h
])

# =============================================
# FUNÇÕES DO SISTEMA
# =============================================
def curva_bomba(Q_P):
    return 260 - 0.002 * Q_P**2

def perdas_carga(Q, L):
    return const_perdas * L * (Q / 3600)**2

def Q_R(t):
    return -0.004 * t**3 + 0.09 * t**2 + 0.1335 * t + 20

def Q_VC_MAX(t):
    return (-1.19333e-7 * t**7 - 4.90754e-5 * t**6 + 3.733e-3 * t**5
            - 0.09621 * t**4 + 1.03965 * t**3 - 3.8645 * t**2 - 1.0124 * t + 75.393)

last_Q_P = 50
def caudal_bomba(t, h_atual):
    global last_Q_P
    Q_R_val = Q_R(t)
    def func(Q_P):
        return (curva_bomba(Q_P) - perdas_carga(Q_P, L_PR) 
                - perdas_carga(Q_P - Q_R_val, L_RF) - 150 - h_atual)
    last_Q_P = fsolve(func, x0=last_Q_P)[0]
    return last_Q_P

# =============================================
# SIMULAÇÃO PRINCIPAL - VERSÃO FINAL (DESLIGA ÀS 13H)
# =============================================
tempo = 24  # horas
dt = 1  # passo (1h)
t_range = np.arange(0, tempo, dt)

# Pré-calcular consumos
Q_R_values = Q_R(t_range)
Q_VC_MAX_values = Q_VC_MAX(t_range)
consumos = Q_R_values + Q_VC_MAX_values

# Arrays para resultados
alturas = [h]
custos = []
estados_bomba = []
Q_P_list = []
penalizacoes = []
consecutivas_abaixo = 0  # Contador de horas consecutivas abaixo do limite

for i, t in enumerate(t_range):
    hora_atual = int(t)
    consumo = consumos[i]
    preco = tarifario[hora_atual]
    bomba = 0
    Q_P = 0
    penalizacao = 0
    
    # Estratégia de controle:
    
    # 1. Período 0h-5h - bomba LIGADA (tarifa mais baixa)
    if 0 <= hora_atual <= 5:
        Q_P = caudal_bomba(t, alturas[-1])
        bomba = 1
        consecutivas_abaixo = 0  # Resetar contador
    
    # 2. Período 6h-13h - manter nível próximo de 7m
    elif 6 <= hora_atual <= 13:
        if alturas[-1] < 6.9:  # Margem de 0.1m abaixo do máximo
            Q_P = caudal_bomba(t, alturas[-1])
            bomba = 1
        consecutivas_abaixo = 0  # Resetar contador
    
    # 3. Período 14h-23h - bomba DESLIGADA
    else:
        # Verificar penalização cumulativa
        if alturas[-1] < h_min:
            consecutivas_abaixo += 1
            penalizacao = 5 * consecutivas_abaixo  # 5, 10, 15, ... euros
        else:
            consecutivas_abaixo = 0
    
    # Cálculo do novo nível
    h_novo = alturas[-1] + (Q_P - consumo) / A
    h_novo = max(0, min(h_max, h_novo))  # Limites físicos
    
    # Cálculo do custo
    custo_energia = power_const * Q_P * curva_bomba(Q_P) * dt * preco if bomba else 0
    custo_total = custo_energia + penalizacao
    
    # Armazenar resultados
    alturas.append(h_novo)
    custos.append(custo_total)
    estados_bomba.append(bomba)
    Q_P_list.append(Q_P)
    penalizacoes.append(penalizacao)

alturas = alturas[1:]

# =============================================
# RESULTADOS E VISUALIZAÇÃO
# =============================================
custo_energia = sum([c - p for c, p in zip(custos, penalizacoes)])
custo_penalizacao = sum(penalizacoes)
custo_total = custo_energia + custo_penalizacao

print(f"\nCusto total em 24h: {custo_total:.2f} €")
print(f" - Custo energia: {custo_energia:.2f} €")
print(f" - Custo penalizações: {custo_penalizacao:.2f} €")
print("Horas de operação da bomba:", [i for i, e in enumerate(estados_bomba) if e])
print("Horas com penalização:", [i for i, p in enumerate(penalizacoes) if p > 0])
print("Penalizações detalhadas:", penalizacoes)

# Gráfico de estratégia
plt.figure(figsize=(14, 10))

# 1. Nível do reservatório
plt.subplot(3, 1, 1)
plt.plot(t_range, alturas, 'b-', linewidth=2, label="Nível (m)")
plt.fill_between(t_range, h_min, h_max, color='green', alpha=0.1, label="Zona segura")
plt.axhline(y=7, color='r', linestyle='--', label="Limite máximo")
plt.axhline(y=6.9, color='orange', linestyle=':', label="Limite operacional")
plt.axhline(y=2, color='r', linestyle='--', label="Limite mínimo")
plt.ylabel("Nível de água (m)")
plt.xticks(range(24))
plt.legend()
plt.grid(True)

# 2. Operação da bomba e penalizações
plt.subplot(3, 1, 2)
plt.bar(t_range, [e*50 for e in estados_bomba], color='blue', alpha=0.5, label="Bomba ligada")
plt.bar(t_range, penalizacoes, color='red', alpha=0.5, label="Penalizações (€)")
plt.ylabel("Operação/Penalizações")
plt.xticks(range(24))
plt.legend()
plt.grid(True)

# 3. Custos acumulados
plt.subplot(3, 1, 3)
plt.plot(t_range, np.cumsum([c - p for c, p in zip(custos, penalizacoes)]), 'b-', label="Custo energia")
plt.plot(t_range, np.cumsum(penalizacoes), 'r-', label="Penalizações")
plt.plot(t_range, np.cumsum(custos), 'g-', linewidth=2, label="Custo total")
plt.xlabel("Hora do dia")
plt.ylabel("Custo acumulado (€)")
plt.xticks(range(24))
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.show()