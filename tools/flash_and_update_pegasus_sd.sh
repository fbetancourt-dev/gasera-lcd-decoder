#!/usr/bin/env bash
# ==============================================================================
# Flasheador y Actualizador de SD para Gasera Pegasus v2 (Orange Pi Zero 2W)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_IMG="/home/fbetancourt/Desktop/Monitor para Gasera Pegasus/pegasus_display_v2.img"
IMG_PATH="${1:-$DEFAULT_IMG}"

# Auto-detección de unidad de tarjeta SD (prioriza adaptador USB /dev/sdb, luego /dev/sda)
if [ -n "$2" ]; then
    TARGET_DRIVE="$2"
elif [ -b "/dev/sdb" ] && [ "$(cat /sys/block/sdb/removable 2>/dev/null)" = "1" ]; then
    TARGET_DRIVE="/dev/sdb"
elif [ -b "/dev/sda" ] && [ "$(cat /sys/block/sda/removable 2>/dev/null)" = "1" ]; then
    TARGET_DRIVE="/dev/sda"
else
    TARGET_DRIVE="/dev/sdb"
fi

echo "======================================================================"
echo "  FLASHEADOR & ACTUALIZADOR SD - GASERA PEGASUS v2"
echo "======================================================================"
echo " Imagen origen:    $IMG_PATH"
echo " Unidad destino:   $TARGET_DRIVE (Lector / Adaptador SD)"
echo " Repositorio base: $SOURCE_REPO"
echo "======================================================================"
echo ""

# Verificaciones
if [ ! -b "$TARGET_DRIVE" ]; then
    echo "❌ Error: La unidad $TARGET_DRIVE no existe o no está conectada."
    echo "Uso: $0 [ruta_imagen.img] [dispositivo_destino (/dev/sdb)]"
    exit 1
fi

if [ ! -f "$IMG_PATH" ]; then
    echo "❌ Error: La imagen $IMG_PATH no fue encontrada."
    exit 1
fi

echo "1. Desmontando particiones activas en $TARGET_DRIVE..."
for part in ${TARGET_DRIVE}*; do
    if mountpoint -q "$part" 2>/dev/null || grep -qs "$part " /proc/mounts; then
        echo "   Desmontando $part..."
        sudo umount -f "$part" || true
    fi
done

echo ""
echo "2. Grabando imagen en la tarjeta SD ($TARGET_DRIVE)..."
echo "   (Esto tomará entre 3 y 6 minutos dependiendo de la velocidad de la SD)"
echo ""
sudo dd if="$IMG_PATH" of="$TARGET_DRIVE" bs=4M status=progress conv=fsync

echo ""
echo "3. Sincronizando datos en hardware..."
sudo sync

echo ""
echo "4. Recargando tabla de particiones..."
sudo partprobe "$TARGET_DRIVE" || true
sleep 3

echo ""
echo "5. Montando partición del sistema operativo (opi_root)..."
MOUNT_DIR="/media/fbetancourt/opi_root"
sudo mkdir -p "$MOUNT_DIR"
sudo mount "${TARGET_DRIVE}1" "$MOUNT_DIR"

echo ""
echo "6. Actualizando software con las mejoras del repositorio..."
TARGET_CODE_DIR="$MOUNT_DIR/home/orangepi/Documents/lcd-display-analyzer"

if [ -d "$TARGET_CODE_DIR" ]; then
    echo "   Directorio destino encontrado: $TARGET_CODE_DIR"
    
    # Copiar archivos raíz actualizados
    sudo cp -v "$SOURCE_REPO/README.md" "$TARGET_CODE_DIR/"
    sudo cp -v "$SOURCE_REPO/lcd_decoder_server.py" "$TARGET_CODE_DIR/"
    sudo cp -v "$SOURCE_REPO/st7565_trace_export.c" "$TARGET_CODE_DIR/"
    sudo cp -r -v "$SOURCE_REPO/static" "$TARGET_CODE_DIR/"
    sudo cp -r -v "$SOURCE_REPO/calibrations" "$TARGET_CODE_DIR/"
    sudo cp -r -v "$SOURCE_REPO/docs" "$TARGET_CODE_DIR/"
    sudo cp -r -v "$SOURCE_REPO/tools" "$TARGET_CODE_DIR/"
    
    # Si existe la estructura de variants/display-variant-2 en la imagen:
    if [ -d "$TARGET_CODE_DIR/variants/display-variant-2" ]; then
        echo "   Sincronizando con variants/display-variant-2..."
        sudo cp -v "$SOURCE_REPO/lcd_decoder_server.py" "$TARGET_CODE_DIR/variants/display-variant-2/"
        sudo cp -v "$SOURCE_REPO/st7565_trace_export.c" "$TARGET_CODE_DIR/variants/display-variant-2/"
        sudo cp -r -v "$SOURCE_REPO/static"/* "$TARGET_CODE_DIR/variants/display-variant-2/static/" 2>/dev/null || true
        sudo cp -r -v "$SOURCE_REPO/calibrations"/* "$TARGET_CODE_DIR/variants/display-variant-2/calibrations/" 2>/dev/null || true
    fi

    # Asegurar que el usuario orangepi (uid 1000) sea el dueño
    sudo chown -R 1000:1000 "$TARGET_CODE_DIR"
    echo "   ✅ Archivos sincronizados con éxito."
else
    echo "⚠️ Advertencia: No se encontró la ruta esperada en la imagen, revisa $MOUNT_DIR/home/orangepi/"
fi

echo ""
echo "7. Desmontando y finalizando de forma segura..."
sudo sync
sudo umount "$MOUNT_DIR"
sudo rmdir "$MOUNT_DIR" 2>/dev/null || true

echo ""
echo "======================================================================"
echo "🎉 ¡LISTO! La tarjeta SD está grabada, actualizada y lista para usar."
echo " Ya puedes retirarla con seguridad e insertarla en la Orange Pi Zero 2W."
echo "======================================================================"
