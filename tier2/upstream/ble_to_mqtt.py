from bleak import BleakClient, BleakScanner
import asyncio, json, time
import paho.mqtt.client as mqtt

SERVICE_UUID = "19B10010-E8F2-537E-4F6C-D104768A1214"
CHAR_UUID    = "19B10011-E8F2-537E-4F6C-D104768A1214"

BROKER   = "3.107.51.150"      # ← Mac上のMosquittoを指定
PORT     = 1883
TOPIC    = "sensors/soil"
DEVICE_ID= "soil-node-01"

mqttc = mqtt.Client()
mqttc.connect(BROKER, PORT, 60)
mqttc.loop_start()

async def main():
    print("Scanning...")
    device = await BleakScanner.find_device_by_name("SoilNode")
    if not device:
        print("Device not found")
        return

    async with BleakClient(device.address) as client:
        print("Connected to", device.name)

        def handle_notify(sender, data):
            raw = int.from_bytes(data, "little")
            payload = {
                "device": DEVICE_ID,
                "timestamp": int(time.time()),
                "soil_raw": raw
            }
            mqttc.publish(TOPIC, json.dumps(payload), qos=1)
            print("Published:", payload)

        await client.start_notify(CHAR_UUID, handle_notify)
        await asyncio.sleep(30.0)  # 30秒購読
        await client.stop_notify(CHAR_UUID)

    mqttc.loop_stop()
    mqttc.disconnect()

asyncio.run(main())
