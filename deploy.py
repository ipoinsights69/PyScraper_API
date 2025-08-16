import os
import subprocess
import sys
from pathlib import Path
import platform

BASE_DIR = Path(__file__).parent.resolve()
VENV_DIR = BASE_DIR / "venv"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"
META_SCRIPT = BASE_DIR / "meta_data.py"
PARSER_SCRIPT = BASE_DIR / "parser.py"
API_SCRIPT = BASE_DIR / "ipo_api.py"

def command_exists(cmd):
    return subprocess.run(f"which {cmd}", shell=True, capture_output=True).returncode == 0

def install_npm():
    system = platform.system()
    if system == "Linux":
        subprocess.run(["sudo", "apt", "update"], check=True)
        subprocess.run(["sudo", "apt", "install", "-y", "npm"], check=True)
    elif system == "Darwin":
        if not command_exists("brew"):
            print("Homebrew not found. Please install Homebrew first: https://brew.sh/")
            sys.exit(1)
        subprocess.run(["brew", "install", "node"], check=True)

def install_lxml_dependencies():
    system = platform.system()
    if system == "Linux":
        subprocess.run(["sudo", "apt", "install", "-y", "libxml2-dev", "libxslt1-dev", "python3-dev"], check=True)
    elif system == "Darwin":
        subprocess.run(["brew", "install", "libxml2", "libxslt"], check=True)
        subprocess.run(["brew", "link", "--force", "libxml2"], check=True)
        subprocess.run(["brew", "link", "--force", "libxslt"], check=True)

# 1. Ensure python3 exists
if not command_exists("python3"):
    print("Python3 not found. Please install Python3 manually.")
    sys.exit(1)

# 2. Ensure pip exists
pip_cmd = "pip3" if command_exists("pip3") else "pip"
if not command_exists(pip_cmd):
    print("pip not found. Installing pip...")
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=True)

# 3. Ensure npm exists
if not command_exists("npm"):
    print("npm not found. Installing npm...")
    install_npm()

# 4. Ensure pm2 exists
if not command_exists("pm2"):
    print("pm2 not found. Installing pm2 globally...")
    subprocess.run(["sudo", "npm", "install", "-g", "pm2"], check=True)

# 5. Install lxml build dependencies
install_lxml_dependencies()

# 6. Create virtual environment
if not VENV_DIR.exists():
    print("Creating virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)

# 7. Upgrade pip, setuptools, wheel in venv
pip_path = VENV_DIR / "bin" / "pip"
python_path = VENV_DIR / "bin" / "python"
subprocess.run([str(pip_path), "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)

# 8. Install dependencies inside venv
print("Installing dependencies in venv...")
subprocess.run([str(pip_path), "install", "-r", str(REQUIREMENTS_FILE)], check=True)

# 9. Create cron shell script
cron_script_path = BASE_DIR / "run_meta_parser.sh"
with open(cron_script_path, "w") as f:
    f.write(f"""#!/bin/bash
source {VENV_DIR}/bin/activate
{python_path} {META_SCRIPT}
{python_path} {PARSER_SCRIPT}
""")
os.chmod(cron_script_path, 0o755)
print(f"Cron script created at {cron_script_path}")

# 10. Schedule cron job every 4 hours
cron_job = f"0 */4 * * * {cron_script_path}\n"
existing_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
if cron_job.strip() not in existing_cron.stdout:
    new_cron = existing_cron.stdout + cron_job
    subprocess.run(["crontab"], input=new_cron, text=True)
    print("Cron job scheduled: meta_data.py -> parser.py every 4 hours")
else:
    print("Cron job already exists")

# 11. Deploy ipo_api.py using PM2 with venv Python
print("Deploying ipo_api.py using PM2 with venv Python...")
subprocess.run(["pm2", "delete", "ipo_api"], check=False)  # remove old instance if any
subprocess.run([
    "pm2", "start", str(API_SCRIPT),
    "--name", "ipo_api",
    "--interpreter", str(python_path)  # ensure venv Python is used
], check=True)

subprocess.run(["pm2", "save"], check=True)

print("Setup completed successfully! Flask and other deps should now be found inside venv.")
