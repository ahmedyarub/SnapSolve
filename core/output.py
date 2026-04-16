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
import re
from pygments import lex
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

_ui_queue = queue.Queue()
_ui_thread = None
_app_callbacks = {}

def render_markdown(text_widget, text_content, fallback_language="python"):
    # Configure tags
    text_widget.tag_configure("bold", font=("Arial", 14, "bold"))
    text_widget.tag_configure("italic", font=("Arial", 14, "italic"))
    text_widget.tag_configure("header1", font=("Arial", 20, "bold"))
    text_widget.tag_configure("header2", font=("Arial", 18, "bold"))
    text_widget.tag_configure("header3", font=("Arial", 16, "bold"))

    # Base Code block styling
    bg_color = "#282a36" # Dracula background
    text_widget.tag_configure("code_block_bg", font=("Courier", 12), background=bg_color, lmargin1=10, lmargin2=10, rmargin=10)
    text_widget.tag_configure("inline_code", font=("Courier", 12), background="#1e1e1e", foreground="#d4d4d4")

    # Table style tag
    text_widget.tag_configure("table", font=("Courier", 12))

    # Pygments Dracula style tags
    style = get_style_by_name('dracula')
    available_tags = set()
    for token, styledef in style:
        tag_name = f"pygments_{str(token)}"
        available_tags.add(tag_name)
        if styledef['color']:
            text_widget.tag_configure(tag_name, font=("Courier", 12), foreground=f"#{styledef['color']}", background=bg_color, lmargin1=10, lmargin2=10, rmargin=10)
        else:
            # Default text color for Dracula
            text_widget.tag_configure(tag_name, font=("Courier", 12), foreground="#f8f8f2", background=bg_color, lmargin1=10, lmargin2=10, rmargin=10)

    lines = text_content.splitlines()
    in_code_block = False
    current_code = []
    current_lang = ""

    in_table = False
    current_table = []

    def format_line_inline(line):
        # Basic inline formatting parsing
        # This uses a regex to split by formatting markers, keeping the markers in the split result
        parts = re.split(r'(\*\*.*?\*\*|\*(?!\s)[^\*]+(?<!\s)\*|\`.*?\`|\$[^\$]+\$)', line)
        for part in parts:
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                text_widget.insert(tk.END, part[2:-2], "bold")
            elif part.startswith("*") and part.endswith("*") and len(part) > 2 and not part.startswith("**"):
                text_widget.insert(tk.END, part[1:-1], "italic")
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                text_widget.insert(tk.END, part[1:-1], "inline_code")
            elif part.startswith("$") and part.endswith("$") and len(part) > 2:
                text_widget.insert(tk.END, part[1:-1], "italic")
            else:
                text_widget.insert(tk.END, part)
        text_widget.insert(tk.END, "\n")

    def flush_table():
        if not current_table:
            return

        # Verify it's a real table: does it have a separator row?
        # A separator row typically consists of pipes and dashes/colons.
        has_separator = False
        for row in current_table:
            # Quick check if it could be a separator
            stripped = row.strip()
            if not stripped:
                continue
            cols = [col.strip() for col in stripped.strip('|').split('|')]
            if all(set(col) <= {'-', ':', ' '} and len(col.strip()) > 0 for col in cols if col.strip()):
                has_separator = True
                break

        if not has_separator:
            # Not a real table, render lines normally
            for row in current_table:
                # Handle horizontal rules
                if row.strip() == "---":
                    text_widget.insert(tk.END, "───────────────\n")
                    continue
                # Handle bullets
                if re.match(r'^\s*\*\s+', row):
                    row = row.replace("*", "•", 1)

                if row.startswith("# "):
                    text_widget.insert(tk.END, row[2:] + "\n", "header1")
                elif row.startswith("## "):
                    text_widget.insert(tk.END, row[3:] + "\n", "header2")
                elif row.startswith("### "):
                    text_widget.insert(tk.END, row[4:] + "\n", "header3")
                else:
                    format_line_inline(row)
            current_table.clear()
            return

        # Split rows into columns
        parsed_rows = []
        for row in current_table:
            # Simple markdown table parsing: split by | and strip whitespace
            cols = [col.strip() for col in row.strip().strip('|').split('|')]
            parsed_rows.append(cols)

        # Determine max width for each column
        col_widths = []
        for row in parsed_rows:
            for i, col in enumerate(row):
                if i >= len(col_widths):
                    col_widths.append(len(col))
                else:
                    col_widths[i] = max(col_widths[i], len(col))

        # Format rows with padding
        for row in parsed_rows:
            # Check if this is a separator row (e.g., |---|---|)
            is_separator = all(set(col.strip()) <= {'-', ':'} and len(col.strip()) > 0 for col in row if col.strip())

            formatted_cols = []
            for i, col in enumerate(row):
                width = col_widths[i] if i < len(col_widths) else len(col)
                if is_separator:
                    formatted_cols.append("-" * width)
                else:
                    formatted_cols.append(col.ljust(width))

            formatted_row = " | ".join(formatted_cols)
            text_widget.insert(tk.END, f"| {formatted_row} |\n", "table")

        current_table.clear()

    def flush_code_block():
        code_text = "\n".join(current_code)
        try:
            lexer = get_lexer_by_name(current_lang)
        except ClassNotFound:
            try:
                lexer = get_lexer_by_name(fallback_language)
            except ClassNotFound:
                try:
                    lexer = guess_lexer(code_text)
                except ClassNotFound:
                    from pygments.lexers.special import TextLexer
                    lexer = TextLexer()

        for ttype, value in lex(code_text + "\n", lexer):
            tag_name = f"pygments_{str(ttype)}"
            # Fallback to parent token types if specific style is missing
            while tag_name not in available_tags and "." in tag_name:
                tag_name = tag_name.rsplit(".", 1)[0]
            if tag_name not in available_tags:
                tag_name = "code_block_bg" # Fallback base style
            text_widget.insert(tk.END, value, tag_name)

    for line in lines:
        if line.strip().startswith("```"):
            if in_table:
                in_table = False
                flush_table()
            if not in_code_block:
                in_code_block = True
                current_code = []
                current_lang = line.strip()[3:].strip()
                if not current_lang:
                    current_lang = fallback_language
            else:
                in_code_block = False
                flush_code_block()
            continue

        if in_code_block:
            current_code.append(line)
        else:
            # Check for table rows (lines containing | with optional whitespace)
            # Standard markdown tables typically start with | or have | somewhere in the line to separate columns.
            # We'll trigger on any line that contains '|' and isn't just empty space, since it could be a row.
            if "|" in line and line.strip() != "":
                if not in_table:
                    in_table = True
                current_table.append(line)
                continue
            elif in_table:
                in_table = False
                flush_table()

            if line.startswith("# "):
                text_widget.insert(tk.END, line[2:] + "\n", "header1")
            elif line.startswith("## "):
                text_widget.insert(tk.END, line[3:] + "\n", "header2")
            elif line.startswith("### "):
                text_widget.insert(tk.END, line[4:] + "\n", "header3")
            else:
                # Handle horizontal rules
                if line.strip() == "---":
                    text_widget.insert(tk.END, "───────────────\n")
                    continue

                # Handle bullets (lines starting with optional whitespace and a *)
                if re.match(r'^\s*\*\s+', line):
                    line = line.replace("*", "•", 1)

                format_line_inline(line)

    if in_code_block:
        flush_code_block()

    if in_table:
        flush_table()

def set_app_callbacks(callbacks):
    global _app_callbacks
    _app_callbacks = callbacks

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

    # Control Panel Window
    panel_window = tk.Toplevel(root)
    panel_window.attributes("-topmost", True)
    panel_window.overrideredirect(True)
    panel_window.attributes("-alpha", 0.9)
    panel_window.withdraw() # Hidden initially
    panel_window.config(bg="#1e1e1e")

    panel_frame = tk.Frame(panel_window, bg="#1e1e1e", bd=2, relief=tk.RAISED)
    panel_frame.pack(fill=tk.BOTH, expand=True)

    # Position panel in bottom left
    def position_panel():
        panel_window.update_idletasks()
        w = panel_window.winfo_reqwidth()
        h = panel_window.winfo_reqheight()
        ws = panel_window.winfo_screenwidth()
        hs = panel_window.winfo_screenheight()
        # Bottom left corner with a small margin
        x = 20
        y = hs - h - 50
        panel_window.geometry(f"{w}x{h}+{x}+{y}")

    def call_main_action(action):
        if action in _app_callbacks:
            # We must use threading or safely dispatch it to main since we don't want to block UI thread
            # Actually, the callbacks in main.py use their own threads, so it's safe to just call them
            try:
                _app_callbacks[action]()
            except Exception as e:
                print(f"Error calling {action}: {e}")

    # Top bar for close button
    panel_top_frame = tk.Frame(panel_frame, bg="#1e1e1e")
    panel_top_frame.pack(fill=tk.X, side=tk.TOP)
    panel_close_btn = tk.Button(panel_top_frame, text="✕", bg="#1e1e1e", fg="gray", bd=0, font=("Arial", 10), command=lambda: toggle_panel(False))
    panel_close_btn.pack(side=tk.RIGHT, padx=5, pady=2)
    panel_close_btn.bind("<Enter>", lambda e: panel_close_btn.config(fg="white"))
    panel_close_btn.bind("<Leave>", lambda e: panel_close_btn.config(fg="gray"))

    # Buttons for the panel
    btn_config = {'bg': '#2d2d2d', 'fg': 'white', 'font': ('Segoe UI Emoji', 14), 'bd': 0, 'padx': 10, 'pady': 5}
    btn_capture = tk.Button(panel_frame, text="📸 Capture", command=lambda: call_main_action('capture'), **btn_config)
    btn_capture.pack(side=tk.TOP, fill=tk.X, pady=2)

    btn_reselect = tk.Button(panel_frame, text="🎯 Reselect", command=lambda: call_main_action('reselect'), **btn_config)
    btn_reselect.pack(side=tk.TOP, fill=tk.X, pady=2)

    btn_multi = tk.Button(panel_frame, text="➕ Multi-select", command=lambda: call_main_action('multi_capture'), **btn_config)
    btn_multi.pack(side=tk.TOP, fill=tk.X, pady=2)

    btn_end_multi = tk.Button(panel_frame, text="✅ End Multi", command=lambda: call_main_action('end_multi_capture'), **btn_config)
    # Pack these later based on state

    btn_cancel_multi = tk.Button(panel_frame, text="❌ Cancel Multi", command=lambda: call_main_action('cancel_multi_capture'), **btn_config)
    # Pack these later based on state

    # Hover effects
    for btn in [btn_capture, btn_reselect, btn_multi, btn_end_multi, btn_cancel_multi]:
        btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#3e3e3e"))
        btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#2d2d2d"))

    is_panel_visible = [False]

    def toggle_panel(show=None):
        if show is None:
            show = not is_panel_visible[0]

        is_panel_visible[0] = show
        if show:
            panel_window.deiconify()
            position_panel()
        else:
            panel_window.withdraw()

    def set_multi_state(in_progress):
        if in_progress:
            btn_end_multi.pack(side=tk.TOP, fill=tk.X, pady=2)
            btn_cancel_multi.pack(side=tk.TOP, fill=tk.X, pady=2)
        else:
            btn_end_multi.pack_forget()
            btn_cancel_multi.pack_forget()
        if is_panel_visible[0]:
            position_panel()

    def process_queue():
        try:
            while True:
                msg = _ui_queue.get_nowait()

                # Check for control panel messages
                if msg.get("type") == "toggle_panel":
                    toggle_panel(msg.get("show"))
                    continue
                elif msg.get("type") == "set_multi_state":
                    set_multi_state(msg.get("in_progress"))
                    continue

                text_content = msg.get("text", "")
                auto_close = msg.get("auto_close", 5000)
                opacity = msg.get("opacity", 0.8)
                is_result = msg.get("is_result", False)
                fallback_lang = msg.get("fallback_language", "python")

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
                    render_markdown(text_widget, text_content, fallback_lang)
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

def toggle_control_panel(show=None):
    init_ui()
    _ui_queue.put({"type": "toggle_panel", "show": show})

def update_multi_state(in_progress):
    init_ui()
    _ui_queue.put({"type": "set_multi_state", "in_progress": in_progress})

def show_popup(text, auto_close=5000, opacity=0.8, is_result=False, fallback_language="python"):
    init_ui()
    _ui_queue.put({"text": text, "auto_close": auto_close, "opacity": opacity, "is_result": is_result, "fallback_language": fallback_language})

def output_result(text, output_modes, voice_id=None, auto_close=False, opacity=0.8, fallback_language="python"):
    if not output_modes:
        output_modes = ['popup'] # Default

    if 'audio' in output_modes:
        speak(text, voice_id)

    if 'popup' in output_modes:
        show_popup(text, auto_close=5000 if auto_close else None, opacity=opacity, is_result=True, fallback_language=fallback_language)
