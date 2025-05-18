import asyncio
import nats

async def main():
    print(f"NATS module: {dir(nats)}")
    
    nc = await nats.connect("nats://localhost:4222")
    print(f"Connected client: {nc}")
    print(f"Client type: {type(nc)}")
    print(f"Client methods: {dir(nc)}")
    await nc.close()

if __name__ == "__main__":
    asyncio.run(main())