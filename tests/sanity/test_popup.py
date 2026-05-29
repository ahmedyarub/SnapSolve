import sys
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

app = QApplication(sys.argv)

view = QWebEngineView()
from PyQt6.QtWebEngineCore import QWebEngineSettings
view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
view.resize(800, 600)

assets_dir = Path(r"e:\Python\SnapSolve\core\web_assets")
popup_html = assets_dir / "popup.html"
url = QUrl.fromLocalFile(str(popup_html))

print(f"Loading URL: {url.toString()}")
view.setUrl(url)

pending = [json.dumps("Hello world from **Python** using `file://`")]

def on_load_finished(ok):
    with open("test_popup.log", "w") as f:
        f.write(f"Load finished: {ok}\n")
    for js_text in pending:
        code = f"updateContent({js_text});"
        view.page().runJavaScript(code)

    def write_html(html):
        with open("test_popup.log", "a", encoding="utf-8") as f:
            f.write(f"\nHTML length: {len(html)}\n")
            f.write("HTML CONTENT:\n")
            f.write(html)
            
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(500, lambda: view.page().toHtml(write_html))

view.loadFinished.connect(on_load_finished)
view.show()

from PyQt6.QtCore import QTimer
QTimer.singleShot(1500, app.quit)

sys.exit(app.exec())


