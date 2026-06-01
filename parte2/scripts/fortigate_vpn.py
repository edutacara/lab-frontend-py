import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FORTIGATE_MGMT = "192.168.50.10"
FORTIGATE_TOKEN = "seu_api_token_aqui"

VPN_CONFIG = {
    "fortigate": {
        "host": FORTIGATE_MGMT,
        "wan_interface": "wan1",
        "local_subnet": "192.168.10.0/24",
        "tunnel_ip": "169.255.1.1",
        "tunnel_mask": "255.255.255.252",
    },
    "paloalto": {
        "wan_ip": "100.64.0.254",
        "tunnel_ip": "169.255.1.2",
    },
    "ipsec": {
        "phase1_name": "VPN-PA-P1",
        "phase2_name": "VPN-PA-P2",
        "psk": "chave_pre_compartilhada",
        "ike_version": 2,
        "proposal": "aes256-sha256",
        "dhgrp": 14,
        "phase2_proposal": "aes256-sha256",
        "pfs": "enable",
        "pfs_group": 14,
    },
    "bgp": {
        "local_as": 65001,
        "router_id": "169.255.1.1",
        "neighbor_ip": "169.255.1.2",
        "neighbor_as": 65002,
        "network": "192.168.10.0/24",
    },
}


class FortigateVPN:
    def __init__(self, host: str, token: str):
        self.base_url = f"https://{host}/api/v2"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.session.verify = False

    def _put(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}/cmdb/{path}"
        resp = self.session.put(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}/{path}"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}/cmdb/{path}"
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def configure_phase1(self) -> None:
        cfg = VPN_CONFIG
        payload = {
            "name": cfg["ipsec"]["phase1_name"],
            "type": "static",
            "interface": cfg["fortigate"]["wan_interface"],
            "remote-gw": cfg["paloalto"]["wan_ip"],
            "ike-version": str(cfg["ipsec"]["ike_version"]),
            "proposal": cfg["ipsec"]["proposal"],
            "dhgrp": str(cfg["ipsec"]["dhgrp"]),
            "psksecret": cfg["ipsec"]["psk"],
        }
        self._post("vpn/ipsec/phase1-interface", payload)
        print(f"[Fortigate] Phase 1 '{cfg['ipsec']['phase1_name']}' configurada.")

    def configure_phase2(self) -> None:
        cfg = VPN_CONFIG
        # Route-based: proxy IDs any/any — o BGP gerencia o roteamento pelo túnel
        payload = {
            "name": cfg["ipsec"]["phase2_name"],
            "phase1name": cfg["ipsec"]["phase1_name"],
            "proposal": cfg["ipsec"]["phase2_proposal"],
            "pfs": cfg["ipsec"]["pfs"],
            "dhgrp": str(cfg["ipsec"]["pfs_group"]),
            "src-subnet": "0.0.0.0/0",
            "dst-subnet": "0.0.0.0/0",
        }
        self._post("vpn/ipsec/phase2-interface", payload)
        print(f"[Fortigate] Phase 2 '{cfg['ipsec']['phase2_name']}' configurada (any/any, route-based).")

    def configure_tunnel_ip(self) -> None:
        cfg = VPN_CONFIG
        payload = {
            "name": cfg["ipsec"]["phase1_name"],
            "ip": cfg["fortigate"]["tunnel_ip"],
            "remote-ip": cfg["paloalto"]["tunnel_ip"],
        }
        self._put(f"vpn/ipsec/phase1-interface/{cfg['ipsec']['phase1_name']}", payload)
        print(f"[Fortigate] IP do túnel configurado: {cfg['fortigate']['tunnel_ip']}.")

    def configure_bgp(self) -> None:
        cfg = VPN_CONFIG["bgp"]
        payload = {
            "as": str(cfg["local_as"]),
            "router-id": cfg["router_id"],
            "neighbor": [
                {
                    "ip": cfg["neighbor_ip"],
                    "remote-as": str(cfg["neighbor_as"]),
                    "update-source": VPN_CONFIG["ipsec"]["phase1_name"],
                    "soft-reconfiguration": "enable",
                }
            ],
            "network": [{"prefix": cfg["network"]}],
        }
        self._put("router/bgp", payload)
        print(f"[Fortigate] BGP AS {cfg['local_as']} configurado — peer {cfg['neighbor_ip']} AS {cfg['neighbor_as']}.")

    def configure_firewall_policy(self) -> None:
        cfg = VPN_CONFIG
        payload = {
            "name": "LAN-to-PA-VPN",
            "srcintf": [{"name": "internal"}],
            "dstintf": [{"name": cfg["ipsec"]["phase1_name"]}],
            "srcaddr": [{"name": "all"}],
            "dstaddr": [{"name": "all"}],
            "action": "accept",
            "schedule": "always",
            "service": [{"name": "ALL"}],
        }
        self._post("firewall/policy", payload)
        print("[Fortigate] Política de firewall criada.")

    def get_tunnel_status(self) -> list:
        data = self._get("monitor/vpn/ipsec")
        results = data.get("results", [])
        return results

    def validate(self) -> bool:
        tunnels = self.get_tunnel_status()
        name = VPN_CONFIG["ipsec"]["phase1_name"]
        for tunnel in tunnels:
            if tunnel.get("name") == name:
                proxyids = tunnel.get("proxyid", [])
                up = sum(1 for p in proxyids if p.get("status") == "up")
                if up > 0:
                    print(f"[Fortigate] Túnel '{name}' ativo ({up} SA(s) up).")
                    return True
                else:
                    print(f"[ALERTA][Fortigate] Túnel '{name}' encontrado mas sem SAs ativas.")
                    return False
        print(f"[ALERTA][Fortigate] Túnel '{name}' não encontrado.")
        return False


def main() -> None:
    fg = FortigateVPN(FORTIGATE_MGMT, FORTIGATE_TOKEN)

    print("=== Configurando VPN no Fortigate ===")
    fg.configure_phase1()
    fg.configure_phase2()
    fg.configure_tunnel_ip()
    fg.configure_bgp()
    fg.configure_firewall_policy()

    print("\n=== Validando túnel ===")
    ok = fg.validate()
    if not ok:
        print("[ALERTA] Verifique os logs do Fortigate: diagnose debug application ike -1")


if __name__ == "__main__":
    main()
