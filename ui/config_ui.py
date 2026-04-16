import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import subprocess
import darkdetect
import sv_ttk
import keyboard

# Add parent to path so we can import config.settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import get_config, save_config, load_profiles, save_profiles, load_prompts


class ConfigUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ScreenQA Configuration")
        self.root.geometry("600x700")

        self.config = get_config()
        self.models_data = self.load_models()
        self.profiles = load_profiles()
        self.prompts = load_prompts()

        self.active_profile_id = self.config.get('active_profile_id', 'prof1')

        self.create_widgets()
        self.load_current_settings()

    def load_models(self):
        try:
            models_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config",
                                       "llm_models.json")
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

        # --- Profile Section ---
        profile_frame = ttk.LabelFrame(main_frame, text="Profile Settings", padding="5")
        profile_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))
        profile_frame.columnconfigure(1, weight=1)

        ttk.Label(profile_frame, text="Active Profile:").grid(row=0, column=0, sticky=tk.W, pady=5)

        profile_sel_frame = ttk.Frame(profile_frame)
        profile_sel_frame.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        profile_sel_frame.columnconfigure(0, weight=1)

        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(profile_sel_frame, textvariable=self.profile_var, state="readonly")
        self.profile_combo.grid(row=0, column=0, sticky=tk.EW)
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_selected)

        ttk.Button(profile_sel_frame, text="Add", command=self.add_profile, width=5).grid(row=0, column=1, padx=(5, 0))
        ttk.Button(profile_sel_frame, text="Delete", command=self.delete_profile, width=6).grid(row=0, column=2,
                                                                                                padx=(5, 0))

        row += 1

        # --- App Settings Section ---
        app_frame = ttk.LabelFrame(main_frame, text="Application Settings", padding="5")
        app_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))
        app_frame.columnconfigure(1, weight=1)
        app_row = 0

        # Output Mode
        ttk.Label(app_frame, text="Output Mode:").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar()
        output_combo = ttk.Combobox(app_frame, textvariable=self.output_var, state="readonly")
        output_combo['values'] = ('popup', 'audio', 'both')
        output_combo.grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        app_row += 1

        # Ollama URL
        ttk.Label(app_frame, text="Ollama URL:").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.ollama_url_var = tk.StringVar()
        ttk.Entry(app_frame, textvariable=self.ollama_url_var).grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        app_row += 1

        # Google GenAI API Key
        ttk.Label(app_frame, text="Google GenAI API Key:").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        ttk.Entry(app_frame, textvariable=self.api_key_var, show="*").grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        app_row += 1

        # Voice ID
        ttk.Label(app_frame, text="Voice ID (TTS):").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.voice_id_var = tk.StringVar()
        ttk.Entry(app_frame, textvariable=self.voice_id_var).grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        app_row += 1

        # Hotkeys
        ttk.Label(app_frame, text="Capture Hotkey:").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.capture_hk_var = tk.StringVar()
        capture_hk_frame = ttk.Frame(app_frame)
        capture_hk_frame.grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        capture_hk_frame.columnconfigure(0, weight=1)
        ttk.Entry(capture_hk_frame, textvariable=self.capture_hk_var, state="readonly").grid(row=0, column=0,
                                                                                             sticky=tk.EW)
        ttk.Button(capture_hk_frame, text="Record", command=lambda: self.record_hotkey(self.capture_hk_var)).grid(row=0,
                                                                                                                  column=1,
                                                                                                                  padx=(
                                                                                                                      5,
                                                                                                                      0))
        app_row += 1

        ttk.Label(app_frame, text="Reselect Hotkey:").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.reselect_hk_var = tk.StringVar()
        reselect_hk_frame = ttk.Frame(app_frame)
        reselect_hk_frame.grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        reselect_hk_frame.columnconfigure(0, weight=1)
        ttk.Entry(reselect_hk_frame, textvariable=self.reselect_hk_var, state="readonly").grid(row=0, column=0,
                                                                                               sticky=tk.EW)
        ttk.Button(reselect_hk_frame, text="Record", command=lambda: self.record_hotkey(self.reselect_hk_var)).grid(
            row=0, column=1, padx=(5, 0))
        app_row += 1

        # Toggle Panel Hotkey
        ttk.Label(app_frame, text="Toggle Panel Hotkey:").grid(row=app_row, column=0, sticky=tk.W, pady=5)
        self.toggle_panel_hk_var = tk.StringVar()
        toggle_panel_hk_frame = ttk.Frame(app_frame)
        toggle_panel_hk_frame.grid(row=app_row, column=1, sticky=tk.EW, pady=5)
        toggle_panel_hk_frame.columnconfigure(0, weight=1)
        ttk.Entry(toggle_panel_hk_frame, textvariable=self.toggle_panel_hk_var, state="readonly").grid(row=0, column=0,
                                                                                               sticky=tk.EW)
        ttk.Button(toggle_panel_hk_frame, text="Record", command=lambda: self.record_hotkey(self.toggle_panel_hk_var)).grid(
            row=0, column=1, padx=(5, 0))
        app_row += 1

        # Run in background
        self.bg_var = tk.BooleanVar()
        ttk.Checkbutton(app_frame, text="Run in background (Tray)", variable=self.bg_var).grid(row=app_row, column=0,
                                                                                               columnspan=2,
                                                                                               sticky=tk.W, pady=5)
        app_row += 1

        # Show Control Panel on Startup
        self.show_control_panel_var = tk.BooleanVar()
        ttk.Checkbutton(app_frame, text="Show Control Panel on Startup", variable=self.show_control_panel_var).grid(row=app_row, column=0,
                                                                                               columnspan=2,
                                                                                               sticky=tk.W, pady=5)
        row += 1

        # --- Active Profile Configuration Section ---
        prof_cfg_frame = ttk.LabelFrame(main_frame, text="Profile Properties", padding="5")
        prof_cfg_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))
        prof_cfg_frame.columnconfigure(1, weight=1)
        prof_row = 0

        # LLM Engine
        ttk.Label(prof_cfg_frame, text="LLM Engine:").grid(row=prof_row, column=0, sticky=tk.W, pady=5)
        self.llm_var = tk.StringVar()
        self.llm_combo = ttk.Combobox(prof_cfg_frame, textvariable=self.llm_var, state="readonly")
        self.llm_combo['values'] = list(self.models_data.keys())
        self.llm_combo.grid(row=prof_row, column=1, sticky=tk.EW, pady=5)
        self.llm_combo.bind("<<ComboboxSelected>>", self.update_models)
        prof_row += 1

        # Model
        ttk.Label(prof_cfg_frame, text="Model:").grid(row=prof_row, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(prof_cfg_frame, textvariable=self.model_var, state="readonly")
        self.model_combo.grid(row=prof_row, column=1, sticky=tk.EW, pady=5)
        prof_row += 1

        # Fallback Model
        ttk.Label(prof_cfg_frame, text="Fallback Model:").grid(row=prof_row, column=0, sticky=tk.W, pady=5)
        self.fallback_model_var = tk.StringVar()
        self.fallback_model_combo = ttk.Combobox(prof_cfg_frame, textvariable=self.fallback_model_var, state="readonly")
        self.fallback_model_combo.grid(row=prof_row, column=1, sticky=tk.EW, pady=5)
        prof_row += 1

        # OCR Engine
        ttk.Label(prof_cfg_frame, text="OCR Engine:").grid(row=prof_row, column=0, sticky=tk.W, pady=5)
        self.ocr_var = tk.StringVar()
        ocr_combo = ttk.Combobox(prof_cfg_frame, textvariable=self.ocr_var, state="readonly")
        ocr_combo['values'] = ('none', 'paddleocr')
        ocr_combo.grid(row=prof_row, column=1, sticky=tk.EW, pady=5)
        prof_row += 1

        # Prompt
        ttk.Label(prof_cfg_frame, text="Prompt:").grid(row=prof_row, column=0, sticky=tk.W, pady=5)
        self.prompt_var = tk.StringVar()
        self.prompt_combo = ttk.Combobox(prof_cfg_frame, textvariable=self.prompt_var, state="readonly")
        self.prompt_combo['values'] = [f"{p['description']} ({p['id']})" for p in self.prompts]
        self.prompt_combo.grid(row=prof_row, column=1, sticky=tk.EW, pady=5)
        prof_row += 1

        row += 1

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Save", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save & Run App", command=self.save_and_run).pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)

    def load_current_settings(self):
        # Update Profiles Combo
        self.update_profile_combo()

        # Select active profile
        self.select_profile_by_id(self.active_profile_id)

        om = self.config.get('output_mode', ['popup'])
        if 'popup' in om and 'audio' in om:
            self.output_var.set('both')
        elif 'audio' in om:
            self.output_var.set('audio')
        else:
            self.output_var.set('popup')

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
            elif hk.get('action') == 'toggle_panel':
                self.toggle_panel_hk_var.set(hk.get('key', ''))

        self.bg_var.set(self.config.get('background', False))
        self.show_control_panel_var.set(self.config.get('show_control_panel', False))

    def update_profile_combo(self):
        profile_names = [f"{p['name']} ({p['id']})" for p in self.profiles]
        self.profile_combo['values'] = profile_names

    def select_profile_by_id(self, prof_id):
        idx = next((i for i, p in enumerate(self.profiles) if p['id'] == prof_id), -1)
        if idx >= 0:
            self.profile_combo.current(idx)
            self.load_profile_settings(self.profiles[idx])
        elif self.profiles:
            self.profile_combo.current(0)
            self.active_profile_id = self.profiles[0]['id']
            self.load_profile_settings(self.profiles[0])

    def load_profile_settings(self, profile):
        self.llm_var.set(profile.get('llm_engine', 'gemini'))
        self.update_models()

        current_model = profile.get('model', '')
        model_ids = [m.get('id') for m in self.models_data.get(self.llm_var.get(), [])]
        if current_model in model_ids:
            self.model_combo.current(model_ids.index(current_model))
        elif model_ids:
            self.model_combo.current(0)

        current_fallback_model = profile.get('fallback_model', 'None')
        fallback_model_ids = ['None'] + [m.get('id') for m in self.models_data.get(self.llm_var.get(), [])]
        if current_fallback_model in fallback_model_ids:
            self.fallback_model_combo.current(fallback_model_ids.index(current_fallback_model))
        else:
            self.fallback_model_combo.current(0)

        self.ocr_var.set(profile.get('ocr_engine', 'none'))

        prompt_id = profile.get('prompt_id', 'default')
        prompt_idx = next((i for i, p in enumerate(self.prompts) if p['id'] == prompt_id), -1)
        if prompt_idx >= 0:
            self.prompt_combo.current(prompt_idx)
        elif self.prompts:
            self.prompt_combo.current(0)

    def add_profile(self):
        # Create a basic new profile
        new_id = f"prof{len(self.profiles) + 1}"
        new_prof = {
            "id": new_id,
            "name": f"New Profile {len(self.profiles) + 1}",
            "llm_engine": "gemini",
            "model": "gemini-2.5-flash-lite",
            "ocr_engine": "none",
            "prompt_id": "default"
        }

        # Save current profile before switching
        self.save_current_profile_settings()

        self.profiles.append(new_prof)
        self.active_profile_id = new_id

        self.update_profile_combo()
        self.select_profile_by_id(new_id)

    def delete_profile(self):
        if len(self.profiles) <= 1:
            messagebox.showwarning("Warning", "Cannot delete the last profile.")
            return

        idx = self.profile_combo.current()
        if idx >= 0:
            del self.profiles[idx]
            self.active_profile_id = self.profiles[0]['id']
            self.update_profile_combo()
            self.select_profile_by_id(self.active_profile_id)

    def on_profile_selected(self, event=None):
        idx = self.profile_combo.current()
        if idx >= 0:
            # Before switching, update the OLD active profile with current UI selections
            self.save_current_profile_settings()

            # Switch to new profile
            new_profile = self.profiles[idx]
            self.active_profile_id = new_profile['id']
            self.load_profile_settings(new_profile)

    def save_current_profile_settings(self):
        # Update the currently active profile in memory
        idx = next((i for i, p in enumerate(self.profiles) if p['id'] == self.active_profile_id), -1)
        if idx >= 0:
            self.profiles[idx]['llm_engine'] = self.llm_var.get()
            self.profiles[idx]['model'] = self.get_selected_model_id()
            self.profiles[idx]['fallback_model'] = self.get_selected_fallback_model_id()
            self.profiles[idx]['ocr_engine'] = self.ocr_var.get()

            prompt_idx = self.prompt_combo.current()
            if prompt_idx >= 0:
                self.profiles[idx]['prompt_id'] = self.prompts[prompt_idx]['id']

    def record_hotkey(self, var):
        # Create a popup dialog to ask user to press keys
        record_win = tk.Toplevel(self.root)
        record_win.title("Record Hotkey")
        record_win.geometry("300x150")
        record_win.transient(self.root)
        record_win.grab_set()

        lbl = ttk.Label(record_win,
                        text="Press your desired key combination...\n(e.g., Ctrl+Shift+A)\n\nPress Escape to cancel.",
                        justify="center")
        lbl.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

        recorded_key = []

        def on_key_event(e):
            if e.event_type == keyboard.KEY_DOWN:
                if e.name == "esc":
                    keyboard.unhook_all()
                    record_win.destroy()
                    return
                # Use keyboard.read_hotkey() logic if needed, but it's simpler to use keyboard.read_hotkey() directly
                # However, read_hotkey blocks. We'll use a slightly different approach.
                pass

        def do_record():
            try:
                # read_hotkey blocks until a hotkey is pressed and released
                hotkey = keyboard.read_hotkey(suppress=False)
                if hotkey and hotkey != "esc":
                    # Use after() to safely update Tkinter variables from a background thread
                    self.root.after(0, lambda: var.set(hotkey))
            except Exception as e:
                print(f"Error recording hotkey: {e}")
            finally:
                # Use after() to safely destroy Tkinter windows from a background thread
                self.root.after(0, lambda: record_win.destroy() if record_win.winfo_exists() else None)

        # Run recording in a separate thread so the UI doesn't freeze
        import threading
        threading.Thread(target=do_record, daemon=True).start()

    def update_models(self, event=None):
        llm = self.llm_var.get()
        models = self.models_data.get(llm, [])
        model_names = [f"{m['name']} ({m['id']})" for m in models]
        self.model_combo['values'] = model_names
        if model_names:
            self.model_combo.current(0)

        fallback_model_names = ["None"] + model_names
        self.fallback_model_combo['values'] = fallback_model_names
        if fallback_model_names:
            self.fallback_model_combo.current(0)

    def get_selected_model_id(self):
        idx = self.model_combo.current()
        if idx >= 0:
            llm = self.llm_var.get()
            return self.models_data[llm][idx]['id']
        return ""

    def get_selected_fallback_model_id(self):
        idx = self.fallback_model_combo.current()
        if idx > 0:
            llm = self.llm_var.get()
            return self.models_data[llm][idx - 1]['id']
        return "None"

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

        fallback_idx = self.fallback_model_combo.current()
        if fallback_idx > 0:
            fallback_model_info = self.models_data[llm][fallback_idx - 1]
            if not fallback_model_info.get('supports_ocr', False) and self.ocr_var.get() == 'none':
                messagebox.showerror("Configuration Error",
                                     f"Fallback Model '{fallback_model_info['name']}' does not support built-in OCR. "
                                     "You must select an OCR Engine (e.g., paddleocr) to use this model.")
                return False

        return True

    def _save(self):
        if not self.validate_settings():
            return False

        # Ensure current profile changes are saved to memory before writing
        self.save_current_profile_settings()

        om = self.output_var.get()
        if om == 'both':
            self.config['output_mode'] = ['popup', 'audio']
        elif om == 'audio':
            self.config['output_mode'] = ['audio']
        else:
            self.config['output_mode'] = ['popup']

        self.config['active_profile_id'] = self.active_profile_id
        self.config['ollama_url'] = self.ollama_url_var.get()
        self.config['google_genai_api_key'] = self.api_key_var.get()

        vid = self.voice_id_var.get()
        self.config['voice_id'] = vid if vid else None

        # We need to preserve other hotkeys (multi_capture etc) that are not exposed in the simple config UI
        # so we fetch existing ones and update just capture, reselect, and toggle_panel
        existing_hotkeys = self.config.get('hotkeys', [])
        updated_hotkeys = []
        for hk in existing_hotkeys:
            if hk['action'] not in ('capture', 'reselect', 'toggle_panel'):
                updated_hotkeys.append(hk)

        updated_hotkeys.append({'action': 'capture', 'key': self.capture_hk_var.get()})
        updated_hotkeys.append({'action': 'reselect', 'key': self.reselect_hk_var.get()})
        updated_hotkeys.append({'action': 'toggle_panel', 'key': self.toggle_panel_hk_var.get()})

        self.config['hotkeys'] = updated_hotkeys

        self.config['background'] = self.bg_var.get()
        self.config['show_control_panel'] = self.show_control_panel_var.get()

        # Remove old legacy keys from config if they exist
        for k in ['llm_engine', 'ocr_engine', 'model']:
            if k in self.config:
                del self.config[k]

        save_config(self.config)
        save_profiles(self.profiles)
        return True

    def save_config(self):
        if self._save():
            messagebox.showinfo("Success", "Configuration saved successfully!")

    def save_and_run(self):
        if self._save():
            self.root.destroy()
            main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

            # Use specific flags on Windows to fully detach the child process so it survives PyCharm's run mode termination
            if os.name == 'nt':
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                subprocess.Popen([sys.executable, main_path], creationflags=creationflags)
            else:
                # For non-Windows OS
                subprocess.Popen([sys.executable, main_path], start_new_session=True)


if __name__ == "__main__":
    root = tk.Tk()

    # Apply OS theme using sv_ttk
    if darkdetect.isDark():
        sv_ttk.set_theme("dark")
    else:
        sv_ttk.set_theme("light")

    app = ConfigUI(root)
    root.mainloop()
