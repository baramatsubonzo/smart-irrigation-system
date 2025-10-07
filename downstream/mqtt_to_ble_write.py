# file: mqtt_to_ble_write.py
import asyncio, json
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt

BROKER = "localhost"
TOPIC_CMD = "command/pump"
PUMP_CHAR = "19B10012-E8F2-537E-4F6C-D104768A1214"

ble_client = None

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

def on_mqtt_message(client, userdata, msg):
    val = parse_onoff(msg.payload.decode())
    if val is None:
        print("Ignore payload:", msg.payload)
        return
    if ble_client and ble_client.is_connected:
        # 非同期ループへ投げる
        asyncio.get_event_loop().create_task(
            ble_client.write_gatt_char(PUMP_CHAR, bytearray([val]), response=False)
        )
        print("BLE write:", val)

async def main():
    global ble_client
    print("Scanning BLE...")
    dev = await BleakScanner.find_device_by_name("SoilNode")
    if not dev:
        print("Device not found"); return

    async with BleakClient(dev.address) as client:
        ble_client = client
        print("Connected to", dev.name)

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
