with open('main.py', 'r') as f:
    content = f.read()

content = content.replace("ScreenshotSource()", "ScreenshotSource(None)")

with open('main.py', 'w') as f:
    f.write(content)
