# Herramientas y Scripts de Utilidad (Pegasus Gasera Decoder)

Esta carpeta contiene las herramientas automatizadas para el flasheo de tarjetas SD, verificación de hardware, pruebas de integración y telemetría del decodificador.

---

## 🛠️ Índice de Herramientas

| Script | Lenguaje | Propósito |
| :--- | :---: | :--- |
| **`flash_and_update_pegasus_sd.sh`** | Bash | Flashea la imagen base de la Orange Pi Zero 2W a la tarjeta SD, monta la partición `opi_root` e inyecta automáticamente el código más reciente del repositorio con todas las mejoras. |
| **`format_sd_32g.sh`** | Bash | Formatea y certifica memorias SD de 32GB en formato FAT32 para verificar que no tengan sectores defectuosos ni seguros de hardware (*Write Protect*) activados. |
| **`test_error_screen.py`** | Python | Prueba automatizada de Selenium que simula una pantalla de error (ej. `NO SURTIR ERR 0100`) y verifica que el *Screen Guard* blanquee la pantalla para proteger contra cifras obsoletas. |
| **`test_live_stream.py`** | Python | Consulta la API REST del servidor decodificador (`/api/live/status`), verifica el estado del streaming y muestra métricas de rendimiento y throughput de eventos SPI. |

---

## 🚀 Uso Rápido

### 1. Flashear y Sincronizar Tarjeta SD para la Orange Pi Zero 2W
```bash
# Auto-detecta el lector/adaptador de tarjeta SD (/dev/sdb o /dev/sda):
./tools/flash_and_update_pegasus_sd.sh

# O especificando manualmente la imagen y unidad:
./tools/flash_and_update_pegasus_sd.sh "/ruta/imagen.img" /dev/sdb
```

### 2. Formatear y Probar Memoria SD de 32 GB
```bash
./tools/format_sd_32g.sh /dev/sdb
```

### 3. Verificar Telemetría y Servidor en Vivo
```bash
python3 tools/test_live_stream.py
```

### 4. Ejecutar Prueba de Protección de Pantalla en Blanco (Screen Guard)
```bash
python3 tools/test_error_screen.py
```
