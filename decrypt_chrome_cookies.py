#!/usr/bin/env python3

import os
import json
import base64
import sqlite3
import subprocess
import binascii
import logging
from Crypto.Cipher import AES

# Setup logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Step 1: Get Decrypted Key from Windows PowerShell
def get_decrypted_key():
    logging.info("Fetching decrypted key using PowerShell...")

    powershell_cmd = [
        "powershell.exe",
        "-Command",
        "Add-Type -AssemblyName System.Security; "
        "$LocalStatePath = 'C:\\Users\\justin.kindrix\\AppData\\Local\\Google\\Chrome\\User Data\\Local State'; "
        "$LocalState = Get-Content $LocalStatePath -Raw | ConvertFrom-Json; "
        "$EncryptedKey = [Convert]::FromBase64String($LocalState.os_crypt.encrypted_key); "
        "if ($EncryptedKey.Length -gt 5) { $EncryptedKey = $EncryptedKey[5..($EncryptedKey.Length-1)]; } "
        "else { Write-Error 'Encrypted key is too short.'; exit 1; }; "
        "$DecryptedKey = [System.Security.Cryptography.ProtectedData]::Unprotect($EncryptedKey, $null, "
        "[System.Security.Cryptography.DataProtectionScope]::CurrentUser); "
        "[BitConverter]::ToString($DecryptedKey) -replace '-', ''"
    ]

    try:
        result = subprocess.run(powershell_cmd, capture_output=True, text=True)

        logging.debug(f"PowerShell stdout: {result.stdout.strip()}")
        logging.debug(f"PowerShell stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            logging.error(f"PowerShell command failed with return code {result.returncode}")
            raise ValueError(f"PowerShell command failed. stderr: {result.stderr.strip()}")

        decrypted_key_hex = result.stdout.strip()
        if not decrypted_key_hex:
            logging.error("Decrypted key output is empty.")
            raise ValueError("Failed to retrieve the decrypted key. No output from PowerShell.")

        # Convert hex to binary
        try:
            decrypted_key = binascii.unhexlify(decrypted_key_hex)
            logging.info("Successfully retrieved and converted the decrypted key.")
            return decrypted_key
        except binascii.Error as e:
            logging.error(f"Failed to convert hex to binary: {e}")
            raise ValueError("Hex conversion failed.")

    except Exception as e:
        logging.exception("Exception occurred while fetching the decrypted key.")
        raise ValueError("Failed to retrieve the decrypted key.") from e


# Step 2: Define the path to the Chrome Cookies database
COOKIES_DB = "/mnt/c/Users/justin.kindrix/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"

# Step 3: Function to decrypt Chrome cookies
def decrypt_cookie(encrypted_value, key):
    try:
        if encrypted_value[:3] != b'v10':
            logging.warning(f"Skipping cookie with invalid encryption format: {encrypted_value[:10]}")
            return "[Invalid Encryption Format]"

        iv = encrypted_value[3:15]  # Extract IV (Initialization Vector)
        encrypted_data = encrypted_value[15:]  # Extract encrypted cookie
        cipher = AES.new(key, AES.MODE_GCM, iv)
        decrypted_value = cipher.decrypt(encrypted_data).decode("utf-8")
        return decrypted_value
    except Exception as e:
        logging.error(f"Cookie decryption failed: {e}")
        return f"[Decryption Failed] {e}"


# Step 4: Fetch cookies from the SQLite database
def fetch_cookies():
    logging.info("Fetching decrypted key...")
    decrypted_key = get_decrypted_key()

    # Connect to SQLite (Copy DB first to prevent lock issues)
    temp_db = "/tmp/chrome_cookies.db"
    
    logging.info(f"Copying Chrome Cookies database to {temp_db} to prevent locks...")
    os.system(f"cp '{COOKIES_DB}' '{temp_db}'")

    logging.info("Connecting to SQLite database...")
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
    cookies = cursor.fetchall()
    logging.info(f"Retrieved {len(cookies)} cookies.")

    conn.close()
    os.remove(temp_db)  # Clean up copied DB
    logging.info("Deleted temporary database copy.")

    # Step 5: Decrypt and print cookies
    for host, name, encrypted_value in cookies:
        decrypted_value = decrypt_cookie(encrypted_value, decrypted_key)
        logging.info(f"Host: {host}, Cookie: {name}, Value: {decrypted_value}")


# Run script
if __name__ == "__main__":
    fetch_cookies()
