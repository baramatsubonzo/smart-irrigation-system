import os
import time
import json
import smtplib
import paho.mqtt.client as mqtt
from email.mime.text import MIMEText

# --- 設定（環境変数で注入） ---
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
SOIL_TOPIC  = "sensors/soil/#"         # ← デバイス別に受ける
PUMP_CMD_TOPIC = "control/pump/#"

SOIL_THRESHOLD = float(os.getenv("SOIL_THRESHOLD", "5.0"))
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "1800"))  # 30分

# --- メール設定 ---
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
TO_EMAIL_ADDRESS = os.getenv("TO_EMAIL_ADDRESS", "")

last_alert_at = {}  # deviceId -> epoch（スパム防止用）

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected rc={rc}")
    client.subscribe(SOIL_TOPIC, qos=1)
    client.subscribe(PUMP_CMD_TOPIC, qos=1)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode(errors="ignore")
    print(f"[MQTT] {topic} {payload}")

    # sensors/soil/<deviceId> を想定
    if topic.startswith("sensors/soil/"):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print("[WARN] JSON decode failed")
            return

        # 統一キー: moisture（%）
        moisture = data.get("moisture")
        deviceId = data.get("deviceId") or topic.split("/", 2)[-1]  # topicから補完

        if isinstance(moisture, (int, float)):
            # クールダウン判定
            now = int(time.time())
            last = last_alert_at.get(deviceId, 0)
            if moisture < SOIL_THRESHOLD and (now - last) >= ALERT_COOLDOWN_SEC:
                print(f"[ALERT] {deviceId} moisture={moisture}% < {SOIL_THRESHOLD}% -> notify")
                ok = send_notification(deviceId, moisture)
                if ok:
                    last_alert_at[deviceId] = now
        else:
            print("[WARN] 'moisture' missing or not a number")

    elif topic.startswith("control/pump/"):
        # ここではログだけ。将来: 検証→ACK publish
        print(f"[CMD] manual command received: {payload}")

def send_notification(deviceId, moisture_level):
    if not (SMTP_SERVER and EMAIL_ADDRESS and EMAIL_PASSWORD and TO_EMAIL_ADDRESS):
        print("[ERROR] SMTP env not set. Skip email.")
        return False

    subject = f"Irrigation Alert [{deviceId}]: Soil too dry"
    body = (
        f"Device: {deviceId}\n"
        f"Moisture: {moisture_level}% (threshold {SOIL_THRESHOLD}%)\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n"
        "Please consider watering the plants."
    )

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = TO_EMAIL_ADDRESS

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[EMAIL] sent")
        return True
    except Exception as e:
        print(f"[EMAIL] failed: {e}")
        return False

client = mqtt.Client(client_id=f"svc-notify-{int(time.time())}", clean_session=True)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever(retry_first_connection=True)
