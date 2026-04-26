import time

import pyautogui
import pyperclip

from config import CYCLE_SOURCE


def cycle_until(target_button):
    while True:
        try:
            if pyautogui.locateCenterOnScreen(target_button, confidence=0.8) is not None:
                return
        except pyautogui.ImageNotFoundException:
            pass

        click_button(CYCLE_SOURCE)
        time.sleep(1)


def poll_button(image_path, visible=True, timeout=10, interval=0.5):
    """
    Polls until an image appears or disappears from the screen.

    Args:
        image_path: Path to the image to search for.
        visible: If True, polls until the image is found. If False, polls until the image is NOT found.
        timeout: Maximum time to wait in seconds.
        interval: Time to wait between checks.

    Returns:
        The (x,y) coordinates of the image if found (and visible=True), or True if visible=False and image disappeared.
        Returns None or False if the condition is not met within the timeout.
    """
    print(f"Polling for image '{image_path}' to be {'visible' if visible else 'hidden'}...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=0.8)
            if visible and location is not None:
                print(f"Image '{image_path}' found at {location}.")
                return location
            elif not visible and location is None:
                print(f"Image '{image_path}' is no longer visible.")
                return True
        except pyautogui.ImageNotFoundException:
            if not visible:
                print(f"Image '{image_path}' is no longer visible.")
                return True

        time.sleep(interval)

    print(f"Timeout reached while waiting for '{image_path}' to be {'visible' if visible else 'hidden'}.")
    return None if visible else False


def find_text(text, popup_x, popup_y):
    retries = 0
    while retries < 10:
        print(f"Clicking second text box at ({popup_x}, {popup_y})...")
        pyautogui.click(x=popup_x, y=popup_y)

        print("Selecting and copying text...")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.5)

        copied_text = pyperclip.paste()
        print(f"\n--- Copied Text ---\n{copied_text}\n-------------------")

        if text.lower() in copied_text.lower():
            return True
        else:
            print(f"\n❌ FAILURE: The word '{text}' was NOT found. Retrying")
            retries += 1

    return False


def click_button(image, timeout=10, check_once=False):
    if check_once:
        try:
            button_location = pyautogui.locateCenterOnScreen(image, confidence=0.8)
            if button_location is None:
                print(f"Could not find the button '{image}' on the screen (checked once).")
                return True
        except pyautogui.ImageNotFoundException:
            print(f"Could not find the button '{image}' on the screen (checked once).")
            return True
    else:
        button_location = poll_button(image, visible=True, timeout=timeout)

        if button_location is None:
            print(f"Could not find the button '{image}' on the screen.")
            return False

    print("Button found! Clicking...")
    pyautogui.click(button_location)

    return True


def minimize_all_windows():
    print("Minimizing all windows...")
    pyautogui.hotkey('win', 'd')
    time.sleep(1)
