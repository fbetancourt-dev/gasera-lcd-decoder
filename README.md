# Gasera LCD Decoder (Universal ST7565 Analyzer)

Analizador y decodificador en tiempo real del bus SPI de displays LCD gráficos **ST7565 / ST7565R** (128x64) para dispensadores de gas LP (Gasera).

Soporta de forma unificada y configurable tanto la **Variante 1** como la **Variante 2** de pantalla, con conmutación en caliente, supervisor de reconexión USB para analizadores lógicos Saleae (fx2lafw), interfaz web ligera y modo Kiosk industrial 24/7.

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

## 🔄 Conmutación de Variantes

La aplicación admite cambio de variante por cuatro vías con precedencia clara:
1. **Selector en la UI:** Selector desplegable directo en la cabecera web. Al cambiar, el canvas remapea la pantalla en tiempo real sin reiniciar la captura ni vaciar el búfer.
2. **Parámetro URL:** `http://IP:8081/lcd_decoder_light.html?variant=1` o `?variant=2`.
3. **API REST:** `POST /api/settings/variant` con `{"variant": "v1"}` o `{"variant": "v2"}`.
4. **Línea de comandos:** `--variant v1` o `--variant v2`.

---

## 🔌 Cableado de Sondas (Saleae Logic 8CH)

| Canal Saleae | Señal LCD | Función |
| --- | --- | --- |
| **D0** | **/CS** | Chip Select (Activo en bajo) |
| **D1** | **SCLK** | Serial Clock |
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

En caso de que el cable USB del analizador lógico se desconecte o haya un reinicio de energía en el dispensador, el **Supervisor de Reconexión en caliente** (`_auto_reconnect_supervisor`) detecta automáticamente el hardware al volver y reanuda el streaming en vivo.
