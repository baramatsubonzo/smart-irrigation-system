# file: mqtt_to_ble_write.py
import asyncio, json
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt

BROKER = "localhost"
TOPIC_CMD = "command/pump"
PUMP_CHAR = "19B10012-E8F2-537E-4F6C-D104768A1214"

ble_client = None
MAIN_LOOP = None

def parse_onoff(payload: str):
    p = payload.strip()
    try:
        j = json.loads(p)
        if isinstance(j, dict) and "on" in j:
            return 1 if bool(j["on"]) else 0
    except Exception:
        pass
    if p in ("1", "0"):  # raw
        return int(p)
    return None

def on_mqtt_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    global ble_client, MAIN_LOOP
    val = parse_onoff(message.payload.decode())
    if val is None:
        print("Ignore payload:", message.payload)
        return
    if not (ble_client and ble_client.is_connected):
        print("BLE not ready:", message.payload)
        return
        # main loop に"スレッドセーフに"コルーチン(途中で止めて、また再開できる関数)を投げる
    fut = asyncio.run_coroutine_threadsafe(
        ble_client.write_gatt_char(PUMP_CHAR, bytearray([val]), response=False),
        MAIN_LOOP
    )
    try:
        fut.result(timeout=2.0)  # 結果を待つ（例外があればここで発生）
        print("BLE write:", val)
    except Exception as e:
        print("Failed to write BLE:", e)

async def main():
    global ble_client, MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    print("Scanning BLE...")
    dev = await BleakScanner.find_device_by_name("SoilNode")
    if not dev:
        print("Device not found"); return

    async with BleakClient(dev) as client:
        ble_client = client
        print("Connected to", getattr(dev, "name", str(dev)))

        # MQTT接続＆購読
        mqc = mqtt.Client()
        mqc.on_message = on_mqtt_message
        mqc.connect(BROKER, 1883, 60)
        mqc.subscribe(TOPIC_CMD, qos=1)
        mqc.loop_start()

        try:
            # ここで待機（Ctrl+Cで終了）
            while True:
                await asyncio.sleep(1)
        finally:
            mqc.loop_stop()
            mqc.disconnect()

asyncio.run(main())
