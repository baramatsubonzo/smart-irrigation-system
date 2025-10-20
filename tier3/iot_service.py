import os
import time
import json
import smtplib
import paho.mqtt.client as mqtt
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Read environment variables from .env file.
load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))

# Subscribe to all soil sensor topics.
SOIL_TOPIC  = "sensors/soil/#"
# Subscribe to all pump command topics.
PUMP_CMD_TOPIC = "control/pump/#"

SOIL_THRESHOLD = float(os.getenv("SOIL_THRESHOLD", "1.0"))
# Prevent spamming alerts within this cooldown period (30 minutes).
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "1800"))

# Email configuration from .env file
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
TO_EMAIL_ADDRESS = os.getenv("TO_EMAIL_ADDRESS", "")

# Dictionary to track last alert times for each device
last_alert_at = {}

# MQTT callback functions.
# 'client' is the MQTT client instance.
# 'userdata' is user-defined data for sharing state between callvackes (None if not set).
# 'flags' is a dictionary with response flags from the broker.
# 'rc' is the connection result. 0 means success. 1-5 indicate various errors.
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected rc={rc}")
    # qos=1 ensures at-least-once delivery.
    client.subscribe(SOIL_TOPIC, qos=1)
    client.subscribe(PUMP_CMD_TOPIC, qos=1)

# Callback when a PUBLISH message is received from the server.
# 'client' is the MQTT client instance.
# 'userdata' is user-defined data for sharing state between callvackes (None if not set).
# 'msg' is an instance of MQTTMessage, which has topic, payload, qos, retain attributes.
def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
        print(f"[MQTT] Received: {topic} -> {payload}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"[WARN] Failed to decode message from {topic}")
        return

    # Get soil value and decice ID from payload.
    moisture = payload.get("soil_raw")
    deviceId = payload.get("device")

    # Validate payload: ensure 'soil_raw' is numeric.
    if not isinstance(moisture, (int, float)):
        print("[WARN] Invalid 'soil_raw': must be numeric.")
        return
    # Validate payload: ensure 'device' field exists.
    if not deviceId:
        print("[WARN] Missing 'device' field in payload.")
        return

    # ②: Evaluate soil moisture against threshold.
    now = time.time()
    # Get last alert time for this device (default to 0 if not found).
    last_alert_time = last_alert_at.get(deviceId, 0)

    if moisture < SOIL_THRESHOLD:
        # Check cooldown period to prevent spamming alerts.
        if (now - last_alert_time) >= ALERT_COOLDOWN_SEC:
            print(f"[ALERT] {deviceId} is too dry ({moisture}). Sending notification...")
            # ③: Send notification (e.g., email).
            success = send_notification(deviceId, moisture)
            if success:
                # Update last alert time on successful notification.
                last_alert_at[deviceId] = now
        else:
            print(f"[INFO] {deviceId} is dry, but in cooldown period. Skipping alert.")

# ③: Function to send email notification.
def send_notification(deviceId, moisture_level):
    subject = f"Smart Irrigation Alert: [{deviceId}] soil is too dry."
    body = (
        f"Device ID: {deviceId}\n"
        f"Current soil moisture: {moisture_level} (Threshold: {SOIL_THRESHOLD})\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "Watering action is recommended.\n"
        "Please check the irrigation system or water the soil if necessary."
    )

    # Create a plain text email message object.
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = TO_EMAIL_ADDRESS

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[EMAIL] Notification for {deviceId} sent successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False

# Main entry point.
if __name__ == "__main__":
    # Create a new MQTT client with a unique ID (using process ID).
    # Clean session ensures no previous subscriptions/messages are retained.
    client = mqtt.Client(client_id=f"tier3-notification-service-{os.getpid()}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    print("[INFO] Connecting to MQTT broker...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    # Keep the client running to receive messages indefinitely.
    client.loop_forever()
