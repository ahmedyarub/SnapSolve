import argparse
import json
import os

CONFIG_FILE = 'config.json'

def load_config():
    config = {
        'api_key': '',
        'output_mode': ['popup'], # Can be 'popup', 'audio', or both
        'hotkey': 'ctrl+alt+shift+s',
        'coordinates': None, # [x1, y1, x2, y2]
        'background': False
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except json.JSONDecodeError:
            print(f"Warning: {CONFIG_FILE} is not a valid JSON. Using default settings.")

    return config

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def parse_args():
    parser = argparse.ArgumentParser(description="Screen Capture & Gemini QA")
    parser.add_argument('--api-key', type=str, help='Gemini API Key')
    parser.add_argument('--output-mode', type=str, nargs='+', choices=['popup', 'audio', 'both'], help='Output mode: popup, audio, both')
    parser.add_argument('--hotkey', type=str, help='Keyboard shortcut to trigger capture (e.g., ctrl+alt+shift+s)')
    parser.add_argument('--coords', type=int, nargs=4, metavar=('X1', 'Y1', 'X2', 'Y2'), help='Capture coordinates')
    parser.add_argument('--background', action='store_true', help='Run in background (system tray)')
    parser.add_argument('--foreground', action='store_true', help='Force run in foreground')

    return parser.parse_args()

def get_config():
    config = load_config()
    args = parse_args()

    if args.api_key:
        config['api_key'] = args.api_key
    if args.output_mode:
        if 'both' in args.output_mode:
            config['output_mode'] = ['popup', 'audio']
        else:
            config['output_mode'] = args.output_mode
    if args.hotkey:
        config['hotkey'] = args.hotkey
    if args.coords:
        config['coordinates'] = args.coords

    if args.background:
        config['background'] = True
    elif args.foreground:
        config['background'] = False

    return config
