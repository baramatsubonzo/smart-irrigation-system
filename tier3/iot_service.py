import os
import time
import json
import smtplib
import paho.mqtt.client as mqtt
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

# --- 設定（環境変数で注入） ---
load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
SOIL_TOPIC  = "sensors/soil/#"         # ← デバイス別に受ける
PUMP_CMD_TOPIC = "control/pump/#"

SOIL_THRESHOLD = float(os.getenv("SOIL_THRESHOLD", "1.0"))
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "1800"))  # 30分は再通知しない

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
    """MQTTでメッセージを受信したときに呼ばれる関数"""
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
        print(f"[MQTT] Received: {topic} -> {payload}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"[WARN] Failed to decode message from {topic}")
        return

    # データから必要な値を取得
    moisture = payload.get("soil_raw") # ラズパイからはrawデータが来ると想定
    deviceId = payload.get("device")

    if not all([isinstance(moisture, (int, float)), deviceId]):
        print("[WARN] Invalid payload format. 'soil_raw' and 'device' are required.")
        return

    # --- ② 評価ロジック ---
    now = time.time()
    last_alert_time = last_alert_at.get(deviceId, 0)

    if moisture < SOIL_THRESHOLD:
        # クールダウン時間を過ぎていれば通知
        if (now - last_alert_time) >= ALERT_COOLDOWN_SEC:
            print(f"[ALERT] {deviceId} is too dry ({moisture}). Sending notification...")
            # --- ③ 通知ロジック ---
            success = send_notification(deviceId, moisture)
            if success:
                # 通知が成功したら、最終通知時刻を更新
                last_alert_at[deviceId] = now
        else:
            print(f"[INFO] {deviceId} is dry, but in cooldown period. Skipping alert.")

def send_notification(deviceId, moisture_level):
    """メールで通知を送信する関数"""
    subject = f"スマート灌漑アラート: [{deviceId}] の土壌が乾燥しています"
    body = (
        f"デバイスID: {deviceId}\n"
        f"現在の土壌水分: {moisture_level} (しきい値: {SOIL_THRESHOLD})\n"
        f"時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "水やりを検討してください。"
    )

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

# --- メイン処理 ---
if __name__ == "__main__":
    client = mqtt.Client(client_id=f"tier3-notification-service-{os.getpid()}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    print("[INFO] Connecting to MQTT broker...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    # 無限ループでメッセージを待ち受ける
    client.loop_forever()
