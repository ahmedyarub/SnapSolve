import sys
import json
import argparse
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QShortcut, QKeySequence


class BottomUI(QWidget):
    def __init__(self, data):
        super().__init__()

        # 1. Set Window Flags
        # FramelessWindowHint: Removes the title bar and borders
        # WindowStaysOnBottomHint: Pushes the window behind all other active windows
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnBottomHint
        )

        # 2. Set background to black
        self.setStyleSheet("background-color: black;")

        # Failsafe: Allow you to close it manually by pressing the 'Escape' key
        self.shortcut = QShortcut(QKeySequence("Esc"), self)
        self.shortcut.activated.connect(self.close)

        # 3. Create labels from the parsed JSON data
        for item in data:
            text = item.get('text', '')
            x = item.get('x', 0)
            y = item.get('y', 0)

            label = QLabel(text, self)
            label.setStyleSheet("color: white; font-weight: bold;")
            label.setFont(QFont("Arial", 28))

            # Adjust size so it doesn't get cut off, then move to exact coordinates
            label.adjustSize()
            label.move(x, y)


def main():
    # Parse the incoming JSON string from the runner script
    parser = argparse.ArgumentParser(description="Display bottom-most text.")
    parser.add_argument('--data', type=str, required=True, help='JSON string of texts and coordinates')
    args = parser.parse_args()

    try:
        parsed_data = json.loads(args.data)
    except json.JSONDecodeError:
        print("Error: Could not parse the provided data.")
        sys.exit(1)

    app = QApplication(sys.argv)
    window = BottomUI(parsed_data)

    # Show fullscreen
    window.showFullScreen()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()