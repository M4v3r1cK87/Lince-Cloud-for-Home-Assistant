import asyncio
import aiohttp
import socketio
import logging
import getpass

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("socket_client_local")

# Configurazione
LOGIN_URL = "https://goldcloud.lince.net/api/sessions"
SOCKET_URL = "https://goldcloud.lince.net/socket.io/"
NAMESPACE = "/socket"

class GoldCloudClient:
    def __init__(self, email, password, centrale_id):
        self.email = email
        self.password = password
        self.centrale_id = centrale_id
        self.token = None
        self.sio = socketio.AsyncClient(logger=True, engineio_logger=True)

        # Listener
        self.sio.on("onStatus", self.on_status, namespace=NAMESPACE)
        self.sio.on("connect", self.on_connect, namespace=NAMESPACE)
        self.sio.on("disconnect", self.on_disconnect, namespace=NAMESPACE)
        self.sio.on("*", self.on_any_event, namespace=NAMESPACE)

    async def login(self):
        async with aiohttp.ClientSession() as session:
            payload = {"email": self.email, "password": self.password}
            async with session.post(LOGIN_URL, json=payload) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    self.token = data.get("token")
                    _LOGGER.info("✅ Login effettuato con successo.")
                else:
                    raise Exception(f"❌ Login fallita: {resp.status}")

    async def connect_socket(self):
        if not self.token:
            raise Exception("Token non disponibile. Esegui prima il login.")

        url = f"{SOCKET_URL}?token={self.token}&system_id={self.centrale_id}"
        await self.sio.connect(
            url,
            transports=["websocket"],
            namespaces=[NAMESPACE],
            wait_timeout=10
        )
        await self.sio.wait()

    async def on_connect(self):
        _LOGGER.info(f"[{self.centrale_id}] 🔌 Connesso al namespace {NAMESPACE}")

    async def on_disconnect(self):
        _LOGGER.warning(f"[{self.centrale_id}] 🔌 Disconnesso dal namespace {NAMESPACE}")

    async def on_status(self, data):
        _LOGGER.info(f"[{self.centrale_id}] 📥 Evento onStatus: {data}")

    async def on_any_event(self, event, data):
        _LOGGER.info(f"[{self.centrale_id}] 📦 Evento generico: {event} -> {data}")

async def main():
    print("🔐 Login GoldCloud")
    email = input("Email: ")
    password = getpass.getpass("Password: ")
    centrale_id = input("ID Centrale: ")

    client = GoldCloudClient(email, password, centrale_id)
    await client.login()
    await client.connect_socket()

if __name__ == "__main__":
    asyncio.run(main())
