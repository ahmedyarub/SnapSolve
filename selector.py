import tkinter as tk

class CoordinateSelector:
    def __init__(self):
        self.root = tk.Tk()
        # Make the window transparent and cover the whole screen
        self.root.attributes("-alpha", 0.3)
        self.root.attributes("-fullscreen", True)
        self.root.config(cursor="cross")

        # Set up variables to store coordinates
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.coordinates = None

        # Bind mouse events
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="gray")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

        # Bind escape key to cancel
        self.root.bind("<Escape>", self.cancel)

    def on_button_press(self, event):
        # Save starting coordinates
        self.start_x = event.x
        self.start_y = event.y

        # Create rectangle if not yet created
        if not self.rect:
            self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=3)

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)

        # Expand rectangle as you drag the mouse
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        # Determine final coordinates
        end_x, end_y = (event.x, event.y)

        # Ensure x1 < x2 and y1 < y2
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        # Save coordinates if the area is valid
        if x2 - x1 > 10 and y2 - y1 > 10:
            self.coordinates = [x1, y1, x2, y2]

        self.root.quit()

    def cancel(self, event):
        self.root.quit()

def get_coordinates():
    selector = CoordinateSelector()
    selector.root.mainloop()
    coords = selector.coordinates
    selector.root.destroy()
    return coords
