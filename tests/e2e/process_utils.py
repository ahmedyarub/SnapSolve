import os
import subprocess
import sys
import threading


def show_test_ui(ui_data):
    import json

    json_data = json.dumps(ui_data)

    print("Launching the UI script...")

    command = [sys.executable, "display_ui.py", "--data", json_data]
    return subprocess.Popen(command)


def init_tests(
    launch_service_func,
    launch_app_func,
    minimize_all_windows_func,
    check_port_in_use_func,
):
    minimize_all_windows_func()

    if check_port_in_use_func("127.0.0.1", 8000):
        print("OCR service is already running. Using existing instance.")
        service_process = None
    else:
        service_process = launch_service_func()

    app_process = launch_app_func()

    return app_process, service_process


def cleanup(main_app, service_process):
    if main_app is not None:
        print("\nCleaning up: Terminating the background process...")
        main_app.kill()
        main_app.wait()
        print("Background process safely closed.")

    if service_process is not None:
        print("\nCleaning up: Terminating the service process...")
        service_process.kill()
        service_process.wait()
        print("Service process safely closed.")


def launch_service(service_script_path, working_dir):
    print(f"Launching '{service_script_path}' in the background...")
    try:
        if not os.path.exists(working_dir):
            print(f"Error: The directory '{working_dir}' does not exist.")
            return None

        command_list = [sys.executable, service_script_path]

        env = os.environ.copy()
        env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

        launched_process = subprocess.Popen(
            command_list,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )
        print("Service script launched.")

        def read_output():
            assert launched_process.stdout is not None
            for line in iter(launched_process.stdout.readline, ""):
                print(f"[OCR Service] {line}", end="")

        threading.Thread(target=read_output, daemon=True).start()

        return launched_process
    except Exception as e:
        print(f"Failed to launch the service script: {e}")
        return None


def launch_app(main_script_path, main_script_args, working_dir):
    print(f"Launching '{main_script_path}' in the background...")
    try:
        if not os.path.exists(working_dir):
            print(f"Error: The directory '{working_dir}' does not exist.")
            return None

        command_list = [sys.executable, main_script_path] + main_script_args

        launched_process = subprocess.Popen(
            command_list,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        print("Second script launched. Waiting for initialization...")

        is_initialized = threading.Event()

        def read_output():
            assert launched_process.stdout is not None
            for line in iter(launched_process.stdout.readline, ""):
                print(line, end="")
                if "Initialization done." in line:
                    is_initialized.set()

        threading.Thread(target=read_output, daemon=True).start()

        if is_initialized.wait(timeout=30):
            print("App is fully loaded.")
            return launched_process
        else:
            print("Error: App initialization timed out.")
            launched_process.kill()
            return None

    except Exception as e:
        print(f"Failed to launch the second script: {e}")
        return None
