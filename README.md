# Gasera LCD Decoder (Universal ST7565 Analyzer)

Analizador y decodificador en tiempo real del bus SPI de displays LCD gráficos **ST7565 / ST7565R** (128x64) para dispensadores de gas LP (Gasera).

Soporta de forma unificada y configurable tanto la **Variante 1** como la **Variante 2** de pantalla, con conmutación en caliente, supervisor de reconexión USB para analizadores lógicos Saleae (`fx2lafw`), interfaz web ligera, reconocimiento OCR continuo de cifras con tolerancia a fallos, protección de pantalla en blanco ante errores de surtidor y modo Kiosk industrial 24/7.

---

## 📌 Variantes de Pantalla Soportadas

| Característica | Variante 1 | Variante 2 (Default) |
| --- | --- | --- |
| **Offset de Columna** | `visibleColumnStart = 3` | `visibleColumnStart = 0` |
| **Mapeo de Páginas** | `"xor-4"` (`page ^ 4`, entrelazado) | `"identity"` (`page`, lineal 0..7) |
| **Paleta Sugerida** | Sepia Classic | Black on White |
| **Comportamiento** | Pantalla ST7565 con margen lateral | Pantalla ST7565 directa sin margen |

---

## 🚀 Inicio Rápido

### 1. Compilar el Decodificador Nativo en C
```bash
gcc -O2 -Wall -Wextra -o st7565_trace_export st7565_trace_export.c
```

### 2. Ejecutar el Servidor
```bash
# Iniciar con Variante 2 (por defecto):
python3 lcd_decoder_server.py --host 0.0.0.0 --port 8081

# Forzar arranque en Variante 1:
python3 lcd_decoder_server.py --host 0.0.0.0 --port 8081 --variant v1
```

Abrir en el navegador:
👉 `http://localhost:8081/`

---

## 👁️ Reconocimiento OCR y Protección de Pantalla en Blanco

El sistema cuenta con un motor OCR optimizado en tiempo real diseñado para operar bajo ruido industrial y transitorios del bus SPI:

1. **Marcadores de Guardia de Pantalla (`$` y `Lt`):**
   - El decodificador supervisa continuamente la presencia de los símbolos de inicio de despacho:
     - Marcador **`$`** (Importe Total): Región `x: 0..17, y: 0..31` (ancho 18 px, alto 32 px).
     - Marcador **`Lt`** (Volumen en Litros): Región `x: 0..17, y: 32..59` (ancho 18 px, alto 28 px).
2. **Protección Automática de Pantalla en Blanco:**
   - Si el dispensador entra en un estado fuera de despacho (por ejemplo, errores como `"NO SURTIR ERR 0100 UNIDAD 0004"`, menús de calibración, pruebas de display o pantalla apagada), los marcadores `$` y `Lt` desaparecen.
   - En ese instante, el display de texto limpio (`View: clean text` / `split`) **se blanquea automáticamente** y oculta tanto las cifras como los símbolos para evitar desplegar cobros o litros desactualizados.
   - En cuanto el dispensador inicia un nuevo despacho y reaparecen los marcadores `$` y `Lt`, los dígitos vigentes se reconocen y se muestran de inmediato.
3. **Tolerancia a Ruido en Dígitos:**
   - El motor OCR tolera pérdida transitoria de comandos de borrado o ruido en píxeles individuales causados por interferencias en el cableado, garantizando que el conteo en tiempo real no se congele ni descarte cifras válidas.

---

## 🖥️ Modos de Vista y Escalado en Pantalla Completa (Fullscreen)

La interfaz ofrece tres modos de visualización y dos políticas de escalado geométrico (`Fullscreen` o `Ctrl+Enter` / `F`):

* **Modos de Vista:**
  * **`View: pixels`:** Renderiza el mapa de bits del display LCD nativo (128×64) con cuadrícula de píxeles y rejilla mayor.
  * **`View: clean text`:** Extrae y muestra únicamente el importe (`$ Total`) y los litros (`Lt`) en tipografía vectorial nítida de alto contraste.
  * **`View: split`:** Muestra ambos displays lado a lado de forma simultánea.

* **Políticas de Aspect Ratio (Aspect):**
  * **`Preserve 2:1 + grid`:** Mantiene estrictamente la relación de aspecto nativa **2.000** del LCD (128×64) en todos los modos, centrando la imagen y evitando deformaciones o truncamiento de texto.
  * **`Stretch to fill`:** Permite que las pantallas se expandan ocupando el 100% del alto y ancho disponible del monitor sin bandas negras.

---

## ⚡ Velocidad del Bus SPI y Telemetría

A partir de las capturas reales a 4 MHz en dispensadores activos:

* **Frecuencia de reloj físico SPI (`SCLK`):** **~1.67 MHz a 2.0 MHz** (periodo de ciclo entre **500 ns y 600 ns** por bit).
* **Frecuencia de muestreo del analizador lógico:** **4.0 MHz** (resolución temporal de 250 ns por muestra).
* **Throughput del flujo en vivo:** **~7,140 bytes SPI / segundo** (aprox. **57.1 kbps** de comandos y datos de display continuos).

---

## 📏 Recomendaciones de Longitud y Cableado del Bus SPI

Debido a que el bus SPI opera a frecuencias de **~2 MHz** con niveles lógicos de alta impedancia (single-ended CMOS/TTL de 3.3V o 5V):

### 1. Conexión Directa (Analizador lógico / Microcontrolador directo al display)
* **Longitud recomendada:** **15 cm a 30 cm**.
* **Longitud máxima admisible:** **50 cm** (en entornos con bajo ruido).

> ⚠️ **¿Por qué evitar cables largos sin transceptores?**
> * **Capacitancia del cable:** Un cable común introduce entre **50 y 100 pF/metro**. A 2 MHz, la capacitancia deforma los flancos del reloj `SCLK`, provocando lecturas corruptas de bits.
> * **Reflexiones y timbrado (*ringing*):** Las líneas sin terminación generan falsos pulsos de reloj en las transiciones rápidas (<20 ns).
> * **Ruido EMI en gaseras:** Los contactores, motores de bombas y válvulas solenoides inducen pulsos electromagnéticos de alta energía en cables sin blindar.

### 2. Buenas Prácticas de Cableado para Mitigar Ruido (hasta 1 metro)
1. **Cable plano con tierras intercaladas:** Utilizar un cable de cinta donde cada línea de señal esté blindada por una línea de tierra adyacente:
   $$\text{GND} \;\;|\;\; \text{CS} \;\;|\;\; \text{GND} \;\;|\;\; \text{SCLK} \;\;|\;\; \text{GND} \;\;|\;\; \text{MOSI} \;\;|\;\; \text{GND} \;\;|\;\; \text{D/C} \;\;|\;\; \text{GND}$$
2. **Resistencias serie (*damping*):** Insertar resistencias de **22 $\Omega$ a 47 $\Omega$** en serie en las líneas `SCLK` y `MOSI` lo más cerca posible de la fuente para amortiguar reflexiones.
3. **Malla apantallada:** Utilizar cable apantallado (shielded) conectando la malla a la tierra del chasis metálico en un único punto (evitando bucles de tierra).

### 3. Soluciones para Distancias Mayores (> 1 metro a 50+ metros)
Para instalaciones donde el decodificador o pantalla auxiliar deba ubicarse lejos del cabezal de la bomba:

| Solución | Distancia Máxima | Aplicación / Descripción |
| :--- | :---: | :--- |
| **Buffers de línea (74LVC244 / 74AHCT125)** | **1 a 3 metros** | Elevan la corriente de excitación para manejar la capacitancia del cable. |
| **SPI Diferencial (RS-422 / LVDS)** | **10 a 50 metros** | Transforma las 4 señales en pares trenzados balanceados (cable Cat5e/Cat6) con alta inmunidad a EMI. |
| **Microcontrolador Puente Local (Recomendada)** | **Ilimitada** | Un microcontrolador pequeño (ej. ESP32 o RP2040) colocado a <20 cm del display captura el SPI localmente y transmite los datos procesados por **RS-485, CAN bus, Ethernet o Wi-Fi**. |

---

## 🔌 Asignación de Canales de Sonda (Saleae Logic 8CH)

| Canal Saleae | Señal LCD | Función |
| --- | --- | --- |
| **D0** | **/CS** | Chip Select (Activo en bajo) |
| **D1** | **SCLK** | Serial Clock (~2 MHz) |
| **D2** | **MOSI / SI** | Datos serie del display |
| **D3** | **A0 / D-C** | Comando (0) / Datos (1) |
| **GND** | **GND** | Tierra de referencia común |

---

## 🖥️ Despliegue en Orange Pi Zero 2W (Kiosk 24/7)

El proyecto incluye servicio systemd y supervisor para operación continua sin intervención humana:

```bash
# Copiar servicio systemd:
sudo cp deploy/lcd-decoder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lcd-decoder.service
```

En caso de que el cable USB del analizador lógico se desconecte o haya un reinicio de energía en el dispensador, el **Supervisor de Reconexión en caliente** (`_auto_reconnect_supervisor`) detecta automáticamente el hardware al volver y reanuda el streaming en vivo. Consulta la guía detallada en [`docs/ORANGE_PI_KIOSK_SETUP.md`](docs/ORANGE_PI_KIOSK_SETUP.md).
