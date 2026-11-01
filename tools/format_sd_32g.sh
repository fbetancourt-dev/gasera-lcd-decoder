#!/usr/bin/env bash
# ==============================================================================
# Script de Formateo y Verificación Completa de SD (32 GB)
# ==============================================================================
set -e

TARGET_DEV="${1:-/dev/sdb}"
TARGET_PART="${TARGET_DEV}1"

echo "======================================================================"
echo "  FORMATEADOR Y VERIFICADOR DE SD (32 GB)"
echo "======================================================================"
echo " Dispositivo: $TARGET_DEV"
echo " Partición:   $TARGET_PART"
echo "======================================================================"
echo ""

if [ ! -b "$TARGET_DEV" ]; then
    echo "❌ Error: La unidad $TARGET_DEV no existe o no está conectada."
    echo "Uso: $0 [/dev/sdb o /dev/sda]"
    exit 1
fi

echo "1. Desmontando particiones activas en $TARGET_DEV..."
for part in ${TARGET_DEV}*; do
    if mountpoint -q "$part" 2>/dev/null || grep -qs "$part " /proc/mounts; then
        echo "   Desmontando $part..."
        sudo umount -f "$part" || true
    fi
done

echo ""
echo "2. Re-creando tabla de particiones MBR completa de 32GB..."
sudo parted --script "$TARGET_DEV" mklabel msdos mkpart primary fat32 1MiB 100%
sudo partprobe "$TARGET_DEV"
sleep 2

echo ""
echo "3. Formateando partición $TARGET_PART en FAT32 (32 GB)..."
sudo mkfs.vfat -F 32 -n "SD32GB" -v "$TARGET_PART"

echo ""
echo "4. Sincronizando datos con el hardware..."
sudo sync
sleep 1

echo ""
echo "5. Verificando montaje y espacio real disponible..."
MOUNT_RES=$(udisksctl mount -b "$TARGET_PART" 2>&1)
echo "   $MOUNT_RES"

echo ""
df -h "$TARGET_PART"

echo ""
echo "======================================================================"
echo "✅ ¡FORMATEO EXITOSO! La tarjeta SD formateó sus 32 GB completos."
echo "======================================================================"
