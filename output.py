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

class PopupMessage:
    def __init__(self, text):
        self.root = tk.Tk()
        # Make the popup appear on top and remove title bar
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)

        # Basic styling for a fast, clean popup
        self.frame = tk.Frame(self.root, bg="black", bd=2, relief=tk.RAISED)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.label = tk.Label(
            self.frame,
            text=text,
            bg="black",
            fg="white",
            font=("Arial", 14),
            padx=20,
            pady=10,
            wraplength=400
        )
        self.label.pack(fill=tk.BOTH, expand=True)

        # Calculate position to be near bottom right, but give some padding
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()

        # Give tkinter time to calculate size
        self.root.update_idletasks()

        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()

        x = ws - w - 50
        y = hs - h - 100

        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Bind click to close
        self.root.bind("<Button-1>", self.close)

        # Auto-close after 5 seconds
        self.root.after(5000, self.close)

    def close(self, event=None):
        self.root.destroy()

def show_popup(text):
    # tkinter needs to run in the main thread of its own context,
    # but we can spin it up and destroy it each time.
    def _popup():
        popup = PopupMessage(text)
        popup.root.mainloop()

    threading.Thread(target=_popup, daemon=True).start()

def output_result(text, output_modes, voice_id=None):
    if not output_modes:
        output_modes = ['popup'] # Default

    if 'audio' in output_modes:
        speak(text, voice_id)

    if 'popup' in output_modes:
        show_popup(text)
