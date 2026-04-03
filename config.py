import argparse
import json
import os

CONFIG_FILE = 'config.json'

def load_config():
    config = {
        'output_mode': ['popup'], # Can be 'popup', 'audio', or both
        'hotkeys': [
            {'action': 'capture', 'key': 'ctrl+alt+shift+s'},
            {'action': 'reselect', 'key': 'ctrl+alt+shift+r'}
        ],
        'coordinates': None, # [x1, y1, x2, y2]
        'background': False,
        'voice_id': None # The TTS voice/playback device ID
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                file_config = json.load(f)

                # Migrate old "hotkey" to "hotkeys" format
                if 'hotkey' in file_config and 'hotkeys' not in file_config:
                    file_config['hotkeys'] = [
                        {'action': 'capture', 'key': file_config['hotkey']},
                        {'action': 'reselect', 'key': 'ctrl+alt+shift+r'}
                    ]
                    del file_config['hotkey']
                elif 'hotkeys' in file_config:
                    # Merge existing actions carefully so we don't overwrite user settings
                    current_actions = {hk['action']: hk['key'] for hk in file_config['hotkeys']}

                    if 'capture' not in current_actions:
                        file_config['hotkeys'].append({'action': 'capture', 'key': 'ctrl+alt+shift+s'})
                    if 'reselect' not in current_actions:
                        file_config['hotkeys'].append({'action': 'reselect', 'key': 'ctrl+alt+shift+r'})

                config.update(file_config)
        except json.JSONDecodeError:
            print(f"Warning: {CONFIG_FILE} is not a valid JSON. Using default settings.")

    return config

def save_config(config):
    # Ensure backward compatibility field is removed before saving
    if 'hotkey' in config:
        del config['hotkey']

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def parse_args():
    parser = argparse.ArgumentParser(description="Screen Capture & Gemini QA")
    parser.add_argument('--output-mode', type=str, nargs='+', choices=['popup', 'audio', 'both'], help='Output mode: popup, audio, both')
    parser.add_argument('--hotkey-capture', type=str, help='Keyboard shortcut to trigger capture (e.g., ctrl+alt+shift+s)')
    parser.add_argument('--hotkey-reselect', type=str, help='Keyboard shortcut to reselect coordinates (e.g., ctrl+alt+shift+r)')
    parser.add_argument('--coords', type=int, nargs=4, metavar=('X1', 'Y1', 'X2', 'Y2'), help='Capture coordinates')
    parser.add_argument('--background', action='store_true', help='Run in background (system tray)')
    parser.add_argument('--foreground', action='store_true', help='Force run in foreground')
    parser.add_argument('--voice-id', type=str, help='TTS Voice ID (often maps to a specific language/playback device setting in the OS)')

    return parser.parse_args()

def get_config():
    config = load_config()
    args = parse_args()

    if args.output_mode:
        if 'both' in args.output_mode:
            config['output_mode'] = ['popup', 'audio']
        else:
            config['output_mode'] = args.output_mode

    if args.hotkey_capture or args.hotkey_reselect:
        # Update specific hotkey actions
        for hk in config['hotkeys']:
            if hk['action'] == 'capture' and args.hotkey_capture:
                hk['key'] = args.hotkey_capture
            if hk['action'] == 'reselect' and args.hotkey_reselect:
                hk['key'] = args.hotkey_reselect

    if args.coords:
        config['coordinates'] = args.coords

    if args.background:
        config['background'] = True
    elif args.foreground:
        config['background'] = False

    if args.voice_id:
        config['voice_id'] = args.voice_id

    return config
