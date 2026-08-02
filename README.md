# tesis-portafolio-cuantitativo-sp500
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

```text
.
├── README.md                   <-- Presentación del proyecto y guía de ejecución
├── requirements.txt             <-- Librerías de Python requeridas
│
├── src/                         <-- Código fuente del modelo
│   ├── 01_Monitore_Regimen_Mercado.py  <-- Monitoreo Risk-On / Risk-Off
│   ├── 02_Rebalanceo Diario por Evento ( Extra-Temporal.py      <-- Script de rebalanceo extraordinario (event-driven)
│   └── 03_Rebalanceo_quincenal.py   <-- Algoritmo de selección y ranking Momentum/Beta
│
└── config/                      <-- Archivos de configuración
    └── portafolio_actual.json   <-- Registro de posiciones vigentes en cartera
