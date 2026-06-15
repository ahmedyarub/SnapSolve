from .base import Sink
from core.output import show_popup
import threading


class PopupSink(Sink):
    def __init__(
        self,
        config,
        show_headers=False,
        main_model_name="",
        fallback_model_name="",
        cancel_event: threading.Event = None,
    ):
        super().__init__(cancel_event)
        self.config = config
        self.accumulated_result = []
        self.accumulated_fallback = []
        self.show_headers = show_headers
        self.main_model_name = main_model_name
        self.fallback_model_name = fallback_model_name

        if self.show_headers:
            self.accumulated_result.append(
                f"## Main Model ({self.main_model_name})\n\n"
            )
            self.accumulated_fallback.append(
                f"## Fallback Model ({self.fallback_model_name})\n\n"
            )

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if self.cancel_event.is_set():
            return

        if "popup" not in self.config.get("output_mode", ["popup"]):
            return

        if replace:
            if is_main:
                self.accumulated_result.clear()
                if self.show_headers:
                    self.accumulated_result.append(
                        f"## Main Model ({self.main_model_name})\n\n"
                    )
            else:
                self.accumulated_fallback.clear()
                if self.show_headers:
                    self.accumulated_fallback.append(
                        f"## Fallback Model ({self.fallback_model_name})\n\n"
                    )

        if is_main:
            self.accumulated_result.append(chunk)
            current_text = "".join(self.accumulated_result)
        else:
            self.accumulated_fallback.append(chunk)
            current_text = "".join(self.accumulated_fallback)

        show_popup(
            current_text,
            auto_close=None,
            opacity=self.config.get("opacity", 0.8),
            is_result=True,
        )
