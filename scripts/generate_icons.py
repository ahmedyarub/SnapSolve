"""Generate all icon sizes for SnapSolve from a source PNG.

Creates:
- assets/icon.ico  (multi-resolution ICO for Windows system tray)
- assets/icon.png  (256x256 PNG for general use)
- Android mipmap-* directories with ic_launcher.png at proper DPI sizes
- Android adaptive icon XML resources
"""

import os
import sys
from PIL import Image

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Source icon — update this path if needed
SOURCE_ICON = sys.argv[1] if len(sys.argv) > 1 else None

if not SOURCE_ICON or not os.path.exists(SOURCE_ICON):
    print(f"Usage: python {__file__} <source_icon.png>")
    sys.exit(1)

# Output directories
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
ANDROID_RES_DIR = os.path.join(
    PROJECT_ROOT, "android_remote_control", "app", "src", "main", "res"
)

# ICO sizes for Windows system tray
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

# Android mipmap sizes (launcher icon)
ANDROID_MIPMAP_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

# Android adaptive icon foreground sizes (108dp * density)
ANDROID_ADAPTIVE_FG_SIZES = {
    "mipmap-mdpi": 108,
    "mipmap-hdpi": 162,
    "mipmap-xhdpi": 216,
    "mipmap-xxhdpi": 324,
    "mipmap-xxxhdpi": 432,
}


def create_ico(source_img, output_path):
    """Create a multi-resolution .ico file."""
    # Pillow ICO plugin: save from the largest image with sizes param
    # to auto-downsample into all requested sizes
    img_256 = source_img.resize((256, 256), Image.LANCZOS)
    img_256.save(output_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"  Created: {output_path} ({len(ICO_SIZES)} sizes)")


def create_android_icons(source_img, res_dir):
    """Create Android mipmap launcher icons at all DPI buckets."""
    for mipmap_dir, size in ANDROID_MIPMAP_SIZES.items():
        out_dir = os.path.join(res_dir, mipmap_dir)
        os.makedirs(out_dir, exist_ok=True)

        resized = source_img.copy()
        resized = resized.resize((size, size), Image.LANCZOS)

        out_path = os.path.join(out_dir, "ic_launcher.png")
        resized.save(out_path, format="PNG", optimize=True)
        print(f"  Created: {out_path} ({size}x{size})")

        # Also save as round icon
        out_path_round = os.path.join(out_dir, "ic_launcher_round.png")
        resized.save(out_path_round, format="PNG", optimize=True)
        print(f"  Created: {out_path_round} ({size}x{size})")


def create_adaptive_foreground(source_img, res_dir):
    """Create foreground images for Android adaptive icons.

    Adaptive icons use a 108dp canvas with the visible area being the inner 72dp.
    The icon content is centered with padding.
    """
    for mipmap_dir, canvas_size in ANDROID_ADAPTIVE_FG_SIZES.items():
        out_dir = os.path.join(res_dir, mipmap_dir)
        os.makedirs(out_dir, exist_ok=True)

        # The visible area is 72/108 of the canvas
        icon_size = int(canvas_size * 72 / 108)
        padding = (canvas_size - icon_size) // 2

        # Create transparent canvas
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

        # Resize icon to fit the safe zone
        resized = source_img.copy()
        resized = resized.resize((icon_size, icon_size), Image.LANCZOS)

        # Paste centered
        canvas.paste(resized, (padding, padding), resized if resized.mode == "RGBA" else None)

        out_path = os.path.join(out_dir, "ic_launcher_foreground.png")
        canvas.save(out_path, format="PNG", optimize=True)
        print(f"  Created: {out_path} ({canvas_size}x{canvas_size}, icon {icon_size}x{icon_size})")


def create_adaptive_icon_xml(res_dir):
    """Create adaptive icon XML resource files."""
    # ic_launcher.xml (adaptive icon definition)
    anydpi_dir = os.path.join(res_dir, "mipmap-anydpi-v26")
    os.makedirs(anydpi_dir, exist_ok=True)

    ic_launcher_xml = '''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
'''

    ic_launcher_round_xml = '''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
'''

    launcher_path = os.path.join(anydpi_dir, "ic_launcher.xml")
    with open(launcher_path, "w", encoding="utf-8") as f:
        f.write(ic_launcher_xml)
    print(f"  Created: {launcher_path}")

    launcher_round_path = os.path.join(anydpi_dir, "ic_launcher_round.xml")
    with open(launcher_round_path, "w", encoding="utf-8") as f:
        f.write(ic_launcher_round_xml)
    print(f"  Created: {launcher_round_path}")

    # Add background color to colors.xml (or create ic_launcher_background.xml)
    values_dir = os.path.join(res_dir, "values")
    colors_path = os.path.join(values_dir, "ic_launcher_background.xml")
    background_xml = '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#1E1E1E</color>
</resources>
'''
    with open(colors_path, "w", encoding="utf-8") as f:
        f.write(background_xml)
    print(f"  Created: {colors_path}")


def main():
    print(f"Loading source icon: {SOURCE_ICON}")
    img = Image.open(SOURCE_ICON).convert("RGBA")
    print(f"  Source size: {img.size[0]}x{img.size[1]}")

    # Create assets directory
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # 1. Windows ICO for system tray
    print("\n--- Windows System Tray Icon ---")
    ico_path = os.path.join(ASSETS_DIR, "icon.ico")
    create_ico(img, ico_path)

    # 2. General PNG icon
    print("\n--- General PNG Icon ---")
    png_path = os.path.join(ASSETS_DIR, "icon.png")
    resized_256 = img.resize((256, 256), Image.LANCZOS)
    resized_256.save(png_path, format="PNG", optimize=True)
    print(f"  Created: {png_path} (256x256)")

    # 3. Android mipmap icons
    print("\n--- Android Launcher Icons ---")
    create_android_icons(img, ANDROID_RES_DIR)

    # 4. Android adaptive icon foreground
    print("\n--- Android Adaptive Icon Foreground ---")
    create_adaptive_foreground(img, ANDROID_RES_DIR)

    # 5. Android adaptive icon XML
    print("\n--- Android Adaptive Icon XML ---")
    create_adaptive_icon_xml(ANDROID_RES_DIR)

    print("\nAll icons generated successfully!")
    print(f"\nSystem tray icon: {ico_path}")
    print(f"General icon: {png_path}")
    print(f"Android icons: {ANDROID_RES_DIR}/mipmap-*/")


if __name__ == "__main__":
    main()
