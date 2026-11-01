#!/usr/bin/env bash
# ==============================================================================
# Emulador QEMU para Gasera Pegasus (Orange Pi Zero 2W - Ubuntu Noble 24.04 ARM64)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QEMU_BIN="/home/fbetancourt/.local/bin/qemu-system-aarch64"
if [ ! -x "$QEMU_BIN" ]; then
    QEMU_BIN="$(which qemu-system-aarch64 2>/dev/null || true)"
fi

KERNEL="$SCRIPT_DIR/noble-server-cloudimg-arm64-vmlinuz-generic"
INITRD="$SCRIPT_DIR/noble-server-cloudimg-arm64-initrd-generic"
OVERLAY="$SCRIPT_DIR/pegasus_qemu_overlay.qcow2"
BASE_IMG="/home/fbetancourt/Desktop/Monitor para Gasera Pegasus/pegasus_display_v3.img"

echo "======================================================================"
echo "  EMULADOR QEMU - ORANGE PI ZERO 2W (GASERA PEGASUS)"
echo "======================================================================"
echo " Binario QEMU: $QEMU_BIN"
echo " Kernel ARM64: $KERNEL"
echo " Initrd ARM64: $INITRD"
echo " Overlay seguro: $OVERLAY"
echo "======================================================================"
echo ""

# Si el overlay no existe o si se solicita reiniciar, lo recreamos
if [ ! -f "$OVERLAY" ] || [ "$1" == "--reset" ]; then
    echo "Creando snapshot seguro copy-on-write ($OVERLAY)..."
    qemu-img create -f qcow2 -b "$BASE_IMG" -F raw "$OVERLAY"
fi

echo "Iniciando máquina virtual ARM64 (Cortex-A53, 2GB RAM, VirtIO GPU)..."
echo "  * Para liberar el ratón en la ventana gráfica: Ctrl + Alt + G"
echo "  * Para pantalla completa: Ctrl + Alt + F"
echo "  * Servidor web de la gasera mapeado a: http://localhost:8082"
echo ""

exec "$QEMU_BIN" \
    -M virt,highmem=on \
    -cpu cortex-a53 \
    -smp 4 \
    -m 2048M \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "root=/dev/vda1 rw console=tty1 console=ttyAMA0 apparmor=0" \
    -drive file="$OVERLAY",format=qcow2,if=none,id=hd0 \
    -device virtio-blk-pci,drive=hd0 \
    -device ramfb \
    -device virtio-gpu-pci \
    -device virtio-keyboard-pci \
    -device virtio-tablet-pci \
    -display gtk
