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

    # Top frame for optional close button
    top_frame = tk.Frame(frame, bg="black")
    top_frame.pack(fill=tk.X, side=tk.TOP)

    close_btn = tk.Button(top_frame, text="X", bg="black", fg="white", bd=0, font=("Arial", 10, "bold"), command=lambda: close_window())
    # Will be packed only when needed

    # Container for content
    content_frame = tk.Frame(frame, bg="black")
    content_frame.pack(fill=tk.BOTH, expand=True)

    # Short text label
    label = tk.Label(
        content_frame,
        text="",
        bg="black",
        fg="white",
        font=("Arial", 14),
        padx=20,
        pady=10,
        wraplength=400
    )

    # Long text widget
    text_widget = tk.Text(
        content_frame,
        bg="black",
        fg="white",
        font=("Arial", 14),
        padx=20,
        pady=10,
        wrap=tk.WORD,
        bd=0,
        highlightthickness=0
    )
    scrollbar = tk.Scrollbar(content_frame, command=text_widget.yview)
    text_widget.config(yscrollcommand=scrollbar.set)

    def position_window():
        root.update_idletasks()
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        ws = root.winfo_screenwidth()
        hs = root.winfo_screenheight()

        # Max out at 50% of screen width/height
        max_w = int(ws * 0.5)
        max_h = int(hs * 0.5)

        # Adjust dimensions if it's too big, but also we should allow the window to grow and shrink properly
        if w > max_w:
            w = max_w
        if h > max_h:
            h = max_h

        x = ws - w - 50
        y = hs - h - 100
        root.geometry(f"{w}x{h}+{x}+{y}")

    def close_window(event=None):
        root.withdraw()

    close_timer = [None]

    def process_queue():
        try:
            while True:
                msg = _ui_queue.get_nowait()
                text_content = msg.get("text", "")
                auto_close = msg.get("auto_close", 5000)
                opacity = msg.get("opacity", 0.8)
                is_result = msg.get("is_result", False)

                root.attributes("-alpha", opacity)

                # Reset UI state
                label.pack_forget()
                text_widget.pack_forget()
                scrollbar.pack_forget()
                close_btn.pack_forget()

                if not auto_close:
                    close_btn.pack(side=tk.RIGHT, padx=5, pady=2)

                word_count = len(text_content.split())
                is_long = is_result and word_count > 10

                if is_long:
                    # Enable, insert, then disable to make read-only
                    text_widget.config(state=tk.NORMAL)
                    text_widget.delete(1.0, tk.END)
                    text_widget.insert(tk.END, text_content)
                    text_widget.config(state=tk.DISABLED)

                    # Dynamically calculate width and height based on content
                    lines = text_content.splitlines()
                    # Calculate max line length to approximate width (capped later)
                    max_line_len = max([len(line) for line in lines] + [10])
                    # Approx characters per line
                    req_width_chars = min(max_line_len, 80)

                    # Calculate total lines accounting for word wrap wrapping
                    total_lines = 0
                    for line in lines:
                         total_lines += max(1, len(line) // req_width_chars)

                    text_widget.config(width=req_width_chars, height=total_lines)

                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                else:
                    label.config(text=text_content)
                    label.pack(fill=tk.BOTH, expand=True)

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

def show_popup(text, auto_close=5000, opacity=0.8, is_result=False):
    init_ui()
    _ui_queue.put({"text": text, "auto_close": auto_close, "opacity": opacity, "is_result": is_result})

def output_result(text, output_modes, voice_id=None, auto_close=False, opacity=0.8):
    if not output_modes:
        output_modes = ['popup'] # Default

    if 'audio' in output_modes:
        speak(text, voice_id)

    if 'popup' in output_modes:
        show_popup(text, auto_close=5000 if auto_close else None, opacity=opacity, is_result=True)
