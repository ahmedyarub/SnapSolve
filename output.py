import pyttsx3
import tkinter as tk
import threading

def speak(text, voice_id=None):
    # Run in a separate thread so it doesn't block the UI or main loop
    def _speak():
        try:
            engine = pyttsx3.init()
            # Maximize speed slightly for faster output
            rate = engine.getProperty('rate')
            engine.setProperty('rate', rate + 25)

            # Set specific playback voice/device configuration if provided
            if voice_id:
                engine.setProperty('voice', voice_id)

            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Error: {e}")

    threading.Thread(target=_speak, daemon=True).start()

import queue

_ui_queue = queue.Queue()
_ui_thread = None

def _ui_loop():
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    root.withdraw() # Hide initially

    frame = tk.Frame(root, bg="black", bd=2, relief=tk.RAISED)
    frame.pack(fill=tk.BOTH, expand=True)

    label = tk.Label(
        frame,
        text="",
        bg="black",
        fg="white",
        font=("Arial", 14),
        padx=20,
        pady=10,
        wraplength=400
    )
    label.pack(fill=tk.BOTH, expand=True)

    def position_window():
        root.update_idletasks()
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        ws = root.winfo_screenwidth()
        hs = root.winfo_screenheight()
        x = ws - w - 50
        y = hs - h - 100
        root.geometry(f"{w}x{h}+{x}+{y}")

    def close_window(event=None):
        root.withdraw()

    root.bind("<Button-1>", close_window)

    close_timer = [None]  # Use list to allow modification in nested function

    def process_queue():
        try:
            while True:
                msg = _ui_queue.get_nowait()
                text = msg.get("text")
                auto_close = msg.get("auto_close", 5000)

                label.config(text=text)
                root.deiconify() # Show window
                position_window()

                if close_timer[0]:
                    root.after_cancel(close_timer[0])
                    close_timer[0] = None

                if auto_close:
                    close_timer[0] = root.after(auto_close, close_window)
        except queue.Empty:
            pass

        root.after(100, process_queue)

    root.after(100, process_queue)
    root.mainloop()

def init_ui():
    global _ui_thread
    if _ui_thread is None:
        _ui_thread = threading.Thread(target=_ui_loop, daemon=True)
        _ui_thread.start()

def show_popup(text, auto_close=5000):
    init_ui()
    _ui_queue.put({"text": text, "auto_close": auto_close})

def output_result(text, output_modes, voice_id=None):
    if not output_modes:
        output_modes = ['popup'] # Default

    if 'audio' in output_modes:
        speak(text, voice_id)

    if 'popup' in output_modes:
        show_popup(text, auto_close=5000)
