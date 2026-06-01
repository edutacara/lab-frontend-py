import time
import requests
import urllib3
from xml.etree import ElementTree as ET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FORTIGATE_MGMT = "192.168.50.10"
FORTIGATE_TOKEN = "seu_api_token_aqui"

PALOALTO_MGMT = "192.168.100.10"
PALOALTO_USER = "admin"
PALOALTO_PASS = "sua_senha_aqui"

TUNNEL_WAIT_SECONDS = 30
PING_SOURCE_PA = "192.168.20.1"
PING_TARGET_FG = "192.168.10.1"
PING_COUNT = 4


def check_fortigate_tunnel() -> bool:
    url = f"https://{FORTIGATE_MGMT}/api/v2/monitor/vpn/ipsec"
    headers = {"Authorization": f"Bearer {FORTIGATE_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        resp.raise_for_status()
        tunnels = resp.json().get("results", [])
        for tunnel in tunnels:
            proxyids = tunnel.get("proxyid", [])
            up = sum(1 for p in proxyids if p.get("status") == "up")
            if up > 0:
                print(f"[Fortigate] Túnel ativo — {up} SA(s) estabelecidas.")
                return True
        print("[ALERTA][Fortigate] Nenhuma SA ativa encontrada.")
        return False
    except requests.RequestException as e:
        print(f"[ERRO][Fortigate] Falha ao verificar túnel: {e}")
        return False


def get_paloalto_api_key() -> str:
    resp = requests.get(
        f"https://{PALOALTO_MGMT}/api",
        params={"type": "keygen", "user": PALOALTO_USER, "password": PALOALTO_PASS},
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    key = root.findtext(".//key")
    if not key:
        raise RuntimeError("Falha ao obter API key do Palo Alto.")
    return key


def check_paloalto_tunnel(api_key: str) -> bool:
    try:
        resp = requests.post(
            f"https://{PALOALTO_MGMT}/api",
            data={
                "type": "op",
                "key": api_key,
                "cmd": "<show><vpn><ipsec-sa></ipsec-sa></vpn></show>",
            },
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        entries = root.findall(".//entry")
        active = [e for e in entries if e.findtext("state") in ("active", "init")]
        if active:
            print(f"[Palo Alto] Túnel ativo — {len(active)} SA(s) encontrada(s).")
            return True
        print("[ALERTA][Palo Alto] Nenhuma SA ativa encontrada.")
        return False
    except requests.RequestException as e:
        print(f"[ERRO][Palo Alto] Falha ao verificar túnel: {e}")
        return False


def ping_through_tunnel(api_key: str) -> bool:
    cmd = f"<test><ping><source>{PING_SOURCE_PA}</source><host>{PING_TARGET_FG}</host><count>{PING_COUNT}</count></ping></test>"
    try:
        resp = requests.post(
            f"https://{PALOALTO_MGMT}/api",
            data={"type": "op", "key": api_key, "cmd": cmd},
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        result = ET.fromstring(resp.text).findtext(".//result") or ""
        if "0 received" in result or "unreachable" in result.lower():
            print(f"[ALERTA] Ping falhou: {result.strip()}")
            return False
        print(f"[OK] Ping de {PING_SOURCE_PA} para {PING_TARGET_FG} bem-sucedido.")
        return True
    except requests.RequestException as e:
        print(f"[ERRO] Falha ao executar ping: {e}")
        return False


def main() -> None:
    print("=== Teste de Conectividade VPN IPSec ===\n")

    print(f"Aguardando {TUNNEL_WAIT_SECONDS}s para negociação IKE...")
    time.sleep(TUNNEL_WAIT_SECONDS)

    fg_ok = check_fortigate_tunnel()

    try:
        api_key = get_paloalto_api_key()
        pa_ok = check_paloalto_tunnel(api_key)
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao Palo Alto: {e}")
        pa_ok = False
        api_key = None

    print()
    if fg_ok and pa_ok and api_key:
        ping_ok = ping_through_tunnel(api_key)
    else:
        ping_ok = False
        print("[ALERTA] Ping não realizado — túnel não está ativo em ambos os lados.")

    print("\n=== Resultado ===")
    print(f"  Fortigate : {'OK' if fg_ok else 'FALHA'}")
    print(f"  Palo Alto : {'OK' if pa_ok else 'FALHA'}")
    print(f"  Ping L2L  : {'OK' if ping_ok else 'FALHA'}")

    if not (fg_ok and pa_ok and ping_ok):
        print("\n[ALERTA] A VPN não está funcionando corretamente. Verifique os logs de IKE em ambos os dispositivos.")


if __name__ == "__main__":
    main()
