from bleak import BleakClient, BleakScanner
import asyncio

CHAR_UUID = "19B10011-E8F2-537E-4F6C-D104768A1214"

async def main():
    device = await BleakScanner.find_device_by_name("SoilNode")
    if not device:
        print("Device not found")
        return

    async with BleakClient(device.address) as client:
        print("Connected to", device.name)
        def callback(sender, data):
            val = int.from_bytes(data, "little")
            print("Soil:", val)
        await client.start_notify(CHAR_UUID, callback)
        await asyncio.sleep(10)
        await client.stop_notify(CHAR_UUID)

asyncio.run(main())
