# tesis-portafolio-cuantitativo-spmo
Tesina Maestria en Finanzas
# Modelo Cuantitativo de Asignación de Activos Core/Satélite con Protocolo Defensivo Híbrido

> **Trabajo Final de Grado / Tesis**  
> **Autor:** Ignacio Valicenti  
> **Institución:** UCEMA  
> **Año:** 2026  

---

## 📋 Descripción del Proyecto

Este repositorio contiene el código fuente, la lógica algorítmica y los generadores de diagramas desarrollados para el modelo cuantitativo de gestión de portafolios presentado en el **Capítulo 2** de la tesis.

El sistema implementa una estrategia de inversión 100% sistemática que combina:
* **Control Macro de Régimen:** Evaluación del índice S&P 500 ($SPY$) frente a su media móvil exponencial de 20 días ($\text{EMA}_{20}$).
* **Módulo Core/Satélite:** Asignación táctica basada en rankings de *Momentum Acelerado* y filtros de volatilidad ($\beta$).
* **Protocolo Defensivo Híbrido:** Mecanismo automático de protección de capital mediante coberturas inversas ($PSQ$), renta fija de corta duración ($SHY$) y liquidez ($BIL$).

---

## 📁 Estructura del Repositorio

.
├── README.md
├── requirements.txt
│
├── src/
│   ├── 01_Monitoreo_regimen_mercado.py
│   │      Evaluador diario del régimen de mercado
│   │      (SPY vs EMA20)
│   │
│   ├── 02_Monitor_Salud_Posiciones.py
│   │      Monitoreo de salud de posiciones abiertas
│   │      (precio vs EMA2 y reglas de protección)
│   │
│   ├── 03_Rebalanceo_Adaptativo.py
│   │      Motor de rebalanceo y asignación Core/Satélite
│   │
│   ├── 04_Rendimiento_Portafolio_vs_SPMO.py
│   │      Cálculo de rendimiento acumulado del portafolio
│   │      y comparación contra el benchmark SPMO
│   │
│   └── 05_Alfa_Error_Riesgo_Activo_del_Portafolio.py
│          Métricas de desempeño:
│          alfa, tracking error,
│          riesgo activo e información relativa
│          respecto al benchmark
