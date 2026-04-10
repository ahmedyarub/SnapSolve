import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import subprocess

# Add parent to path so we can import config.settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import get_config, save_config

class ConfigUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ScreenQA Configuration")
        self.root.geometry("500x600")

        self.config = get_config()
        self.models_data = self.load_models()

        self.create_widgets()
        self.load_current_settings()

    def load_models(self):
        try:
            models_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm_models.json")
            with open(models_path, "r") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showwarning("Warning", f"Could not load llm_models.json: {e}")
            return {
                "gemini": [{"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite", "supports_ocr": False}],
                "ollama": [{"id": "llama3", "name": "Llama 3", "supports_ocr": False}],
                "google-genai": [{"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "supports_ocr": False}]
            }

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        # Output Mode
        ttk.Label(main_frame, text="Output Mode:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar()
        output_combo = ttk.Combobox(main_frame, textvariable=self.output_var, state="readonly")
        output_combo['values'] = ('popup', 'audio', 'both')
        output_combo.grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # OCR Engine
        ttk.Label(main_frame, text="OCR Engine:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.ocr_var = tk.StringVar()
        ocr_combo = ttk.Combobox(main_frame, textvariable=self.ocr_var, state="readonly")
        ocr_combo['values'] = ('none', 'paddleocr')
        ocr_combo.grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # LLM Engine
        ttk.Label(main_frame, text="LLM Engine:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.llm_var = tk.StringVar()
        self.llm_combo = ttk.Combobox(main_frame, textvariable=self.llm_var, state="readonly")
        self.llm_combo['values'] = list(self.models_data.keys())
        self.llm_combo.grid(row=row, column=1, sticky=tk.EW, pady=5)
        self.llm_combo.bind("<<ComboboxSelected>>", self.update_models)
        row += 1

        # Model
        ttk.Label(main_frame, text="Model:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(main_frame, textvariable=self.model_var, state="readonly")
        self.model_combo.grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # Ollama URL
        ttk.Label(main_frame, text="Ollama URL:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.ollama_url_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.ollama_url_var).grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # Google GenAI API Key
        ttk.Label(main_frame, text="Google GenAI API Key:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.api_key_var, show="*").grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # Voice ID
        ttk.Label(main_frame, text="Voice ID (TTS):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.voice_id_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.voice_id_var).grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # Hotkeys
        ttk.Label(main_frame, text="Capture Hotkey:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.capture_hk_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.capture_hk_var).grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        ttk.Label(main_frame, text="Reselect Hotkey:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.reselect_hk_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.reselect_hk_var).grid(row=row, column=1, sticky=tk.EW, pady=5)
        row += 1

        # Run in background
        self.bg_var = tk.BooleanVar()
        ttk.Checkbutton(main_frame, text="Run in background (Tray)", variable=self.bg_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Save", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save & Run App", command=self.save_and_run).pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)

    def load_current_settings(self):
        om = self.config.get('output_mode', ['popup'])
        if 'popup' in om and 'audio' in om:
            self.output_var.set('both')
        elif 'audio' in om:
            self.output_var.set('audio')
        else:
            self.output_var.set('popup')

        self.ocr_var.set(self.config.get('ocr_engine', 'none'))
        self.llm_var.set(self.config.get('llm_engine', 'gemini'))

        self.update_models()
        current_model = self.config.get('model', '')

        # Select current model if exists in list, else first
        model_ids = [m.get('id') for m in self.models_data.get(self.llm_var.get(), [])]
        if current_model in model_ids:
            self.model_combo.current(model_ids.index(current_model))
        elif model_ids:
            self.model_combo.current(0)

        self.ollama_url_var.set(self.config.get('ollama_url', 'http://localhost:11434'))
        self.api_key_var.set(self.config.get('google_genai_api_key', ''))

        vid = self.config.get('voice_id')
        self.voice_id_var.set(vid if vid else '')

        hotkeys = self.config.get('hotkeys', [])
        for hk in hotkeys:
            if hk.get('action') == 'capture':
                self.capture_hk_var.set(hk.get('key', ''))
            elif hk.get('action') == 'reselect':
                self.reselect_hk_var.set(hk.get('key', ''))

        self.bg_var.set(self.config.get('background', False))

    def update_models(self, event=None):
        llm = self.llm_var.get()
        models = self.models_data.get(llm, [])
        model_names = [f"{m['name']} ({m['id']})" for m in models]
        self.model_combo['values'] = model_names
        if model_names:
            self.model_combo.current(0)

    def get_selected_model_id(self):
        idx = self.model_combo.current()
        if idx >= 0:
            llm = self.llm_var.get()
            return self.models_data[llm][idx]['id']
        return ""

    def validate_settings(self):
        idx = self.model_combo.current()
        if idx < 0:
            messagebox.showerror("Error", "Please select a model.")
            return False

        llm = self.llm_var.get()
        model_info = self.models_data[llm][idx]

        if not model_info.get('supports_ocr', False) and self.ocr_var.get() == 'none':
            messagebox.showerror("Configuration Error",
                f"Model '{model_info['name']}' does not support built-in OCR. "
                "You must select an OCR Engine (e.g., paddleocr) to use this model.")
            return False

        return True

    def _save(self):
        if not self.validate_settings():
            return False

        om = self.output_var.get()
        if om == 'both':
            self.config['output_mode'] = ['popup', 'audio']
        elif om == 'audio':
            self.config['output_mode'] = ['audio']
        else:
            self.config['output_mode'] = ['popup']

        self.config['ocr_engine'] = self.ocr_var.get()
        self.config['llm_engine'] = self.llm_var.get()
        self.config['model'] = self.get_selected_model_id()
        self.config['ollama_url'] = self.ollama_url_var.get()
        self.config['google_genai_api_key'] = self.api_key_var.get()

        vid = self.voice_id_var.get()
        self.config['voice_id'] = vid if vid else None

        self.config['hotkeys'] = [
            {'action': 'capture', 'key': self.capture_hk_var.get()},
            {'action': 'reselect', 'key': self.reselect_hk_var.get()}
        ]

        self.config['background'] = self.bg_var.get()

        save_config(self.config)
        return True

    def save_config(self):
        if self._save():
            messagebox.showinfo("Success", "Configuration saved successfully!")

    def save_and_run(self):
        if self._save():
            self.root.destroy()
            main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
            # Run the main app
            subprocess.Popen([sys.executable, main_path])

if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigUI(root)
    root.mainloop()
