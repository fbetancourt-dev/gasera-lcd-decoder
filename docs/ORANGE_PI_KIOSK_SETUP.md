# Orange Pi Zero 2W Kiosk & Always-On Setup Guide

This document describes the complete deployment, autostart, kiosk fullscreen, and power management configuration for running the ST7565 LCD Decoder on an **Orange Pi Zero 2W** (or similar Linux SBC) in a 24/7 industrial kiosk environment.

---

## 📌 1. Physical Probe & PCB Wiring Reference

Connect the Saleae Logic 8-channel USB logic analyzer to the ST7565 display bus on the Pegasus CPU/Display board (**5505 Reg CPU 1v5**) as follows:

| PCB Pin (Pegasus) | Wire Color | Logic Analyzer Channel | LCD Signal | Description |
| :---: | :---: | :---: | :---: | --- |
| **Pin 1** | **White** | **GND** | **GND** | Shared Reference Ground (0V) |
| **Pin 11** | **Black** | **D0 (CH1 / ch0)** | **/CS** | Active-low Chip Select |
| **Pin 12** | **Brown** | **D1 (CH2 / ch1)** | **SCLK** | Serial Clock (~1.67–2.0 MHz) |
| **Pin 13** | **Red** | **D2 (CH3 / ch2)** | **MOSI / SI** | Serial Display Data (Master Out -> LCD) |
| **Pin 14** | **Orange** | **D3 (CH4 / ch3)** | **A0 / D-C** | Command (0) / Data (1) Selection |

*(For full wiring diagrams, PCB solder photos, and harness fabrication specs, see [`docs/HARDWARE_WIRING_GUIDE.md`](HARDWARE_WIRING_GUIDE.md)).*

---

## 🚀 2. Automatic Boot Service (Systemd)

Create the systemd service file at `/etc/systemd/system/lcd-decoder.service`:

```ini
[Unit]
Description=LCD Display Decoder Variant 2 Service
After=network.target

[Service]
Type=simple
User=orangepi
WorkingDirectory=/home/orangepi/Documents/lcd-display-analyzer
ExecStart=/usr/bin/python3 /home/orangepi/Documents/lcd-display-analyzer/variants/display-variant-2/lcd_decoder_server.py --host 0.0.0.0 --port 8081
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lcd-decoder.service
```

---

## 🔌 3. Automatic USB Hardware Reconnection

`variants/display-variant-2/lcd_decoder_server.py` includes a background `LiveCapture` supervisor thread. 
- If the Saleae USB cable is disconnected or power cycles, the supervisor gracefully catches the state and scans the USB bus (`fx2lafw`).
- When the USB cable is reconnected, live stream capture automatically resumes without requiring a server reboot or user interaction.

---

## 🖥️ 4. Desktop Kiosk Autostart (Firefox ESR / Chromium)

Create the autostart desktop entry at `~/.config/autostart/lcd-kiosk.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=LCD Display Decoder Kiosk
Comment=Autostart LCD Decoder Kiosk Fullscreen
Exec=firefox-esr --kiosk "http://127.0.0.1:8081/lcd_decoder_light.html"
Terminal=false
X-GNOME-Autostart-enabled=true
```

*(Note: In `lcd_decoder_light.html`, the default view mode is set to `clean` and scaling to `stretch` so the clean text display ($ Total & Lt Litros) fills 100% of the screen without black margin bars).*

---

## 🛡️ 5. Disabling Sleep Mode, Screen Blanking & DPMS (Always-On Display)

To ensure the display never turns off, blacks out, or goes into sleep mode, apply the following 4-layer configuration:

### A. Disable X11 DPMS in LightDM
Create `/etc/lightdm/lightdm.conf.d/50-no-dpms.conf`:
```ini
[Seat:*]
xserver-command=X -s 0 -dpms
```

### B. Mask Systemd Sleep & Suspend Targets
```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

### C. Autostart `xset` Command
Create `~/.config/autostart/disable-dpms.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Disable Screen Blanking and Sleep
Exec=sh -c "xset s off; xset -dpms; xset s noblank; xset s 0 0"
Terminal=false
X-GNOME-Autostart-enabled=true
```

### D. Disable XFCE Power Manager & Screensaver
```bash
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -s false --create -t bool
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/blank-on-ac -s 0 --create -t int
xfconf-query -c xfce4-screensaver -p /saver/enabled -s false --create -t bool
```
