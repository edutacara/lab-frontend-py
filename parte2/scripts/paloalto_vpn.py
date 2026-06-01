import requests
import urllib3
from xml.etree import ElementTree as ET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PALOALTO_MGMT = "192.168.100.10"
PALOALTO_USER = "admin"
PALOALTO_PASS = "sua_senha_aqui"

VPN_CONFIG = {
    "paloalto": {
        "host": PALOALTO_MGMT,
        "wan_interface": "ethernet1/1",
        "tunnel_interface": "tunnel.1",
        "tunnel_ip": "169.255.1.2/30",
        "local_subnet": "192.168.20.0/24",
        "zone_trust": "trust",
        "zone_vpn": "vpn",
    },
    "fortigate": {
        "wan_ip": "100.64.0.1",
        "tunnel_ip": "169.255.1.1",
    },
    "ipsec": {
        "ike_crypto_profile": "IKE-AES256-SHA256",
        "ipsec_crypto_profile": "IPSEC-AES256-SHA256",
        "ike_gateway": "GW-FORTIGATE",
        "tunnel_name": "TUNNEL-FORTIGATE",
        "psk": "chave_pre_compartilhada",
        "dh_group": "group14",
        "encryption": "aes-256-cbc",
        "hash": "sha256",
        "lifetime_ike": 86400,
        "lifetime_ipsec": 3600,
    },
    "bgp": {
        "local_as": 65002,
        "router_id": "169.255.1.2",
        "neighbor_ip": "169.255.1.1",
        "neighbor_as": 65001,
        "network": "192.168.20.0/24",
    },
}


class PaloAltoVPN:
    def __init__(self, host: str, username: str, password: str):
        self.base_url = f"https://{host}/api"
        self.session = requests.Session()
        self.session.verify = False
        self.api_key = self._get_api_key(username, password)

    def _get_api_key(self, username: str, password: str) -> str:
        resp = self.session.get(
            self.base_url,
            params={"type": "keygen", "user": username, "password": password},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        key = root.findtext(".//key")
        if not key:
            raise RuntimeError("Falha ao obter API key do Palo Alto.")
        print("[Palo Alto] API key obtida com sucesso.")
        return key

    def _set_config(self, xpath: str, element: str) -> None:
        resp = self.session.post(
            self.base_url,
            data={
                "type": "config",
                "action": "set",
                "key": self.api_key,
                "xpath": xpath,
                "element": element,
            },
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        status = root.get("status")
        if status != "success":
            msg = root.findtext(".//msg") or resp.text
            raise RuntimeError(f"Erro na configuração: {msg}")

    def _op(self, cmd: str) -> ET.Element:
        resp = self.session.post(
            self.base_url,
            data={"type": "op", "key": self.api_key, "cmd": cmd},
        )
        resp.raise_for_status()
        return ET.fromstring(resp.text)

    def commit(self) -> None:
        resp = self.session.post(
            self.base_url,
            data={"type": "commit", "key": self.api_key, "cmd": "<commit></commit>"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        job_id = root.findtext(".//job")
        print(f"[Palo Alto] Commit iniciado (job {job_id}). Aguarde a conclusão.")

    def configure_ike_crypto_profile(self) -> None:
        cfg = VPN_CONFIG["ipsec"]
        xpath = f"/config/devices/entry[@name='localhost.localdomain']/network/ike/crypto-profiles/ike-crypto-profiles/entry[@name='{cfg['ike_crypto_profile']}']"
        element = f"""
        <encryption><member>{cfg['encryption']}</member></encryption>
        <hash><member>{cfg['hash']}</member></hash>
        <dh-group><member>{cfg['dh_group']}</member></dh-group>
        <lifetime><seconds>{cfg['lifetime_ike']}</seconds></lifetime>
        """
        self._set_config(xpath, element)
        print(f"[Palo Alto] IKE Crypto Profile '{cfg['ike_crypto_profile']}' configurado.")

    def configure_ipsec_crypto_profile(self) -> None:
        cfg = VPN_CONFIG["ipsec"]
        xpath = f"/config/devices/entry[@name='localhost.localdomain']/network/ike/crypto-profiles/ipsec-crypto-profiles/entry[@name='{cfg['ipsec_crypto_profile']}']"
        element = f"""
        <esp>
          <encryption><member>{cfg['encryption']}</member></encryption>
          <authentication><member>{cfg['hash']}</member></authentication>
        </esp>
        <dh-group>{cfg['dh_group']}</dh-group>
        <lifetime><seconds>{cfg['lifetime_ipsec']}</seconds></lifetime>
        """
        self._set_config(xpath, element)
        print(f"[Palo Alto] IPSec Crypto Profile '{cfg['ipsec_crypto_profile']}' configurado.")

    def configure_ike_gateway(self) -> None:
        cfg = VPN_CONFIG
        xpath = f"/config/devices/entry[@name='localhost.localdomain']/network/ike/gateway/entry[@name='{cfg['ipsec']['ike_gateway']}']"
        element = f"""
        <authentication><pre-shared-key><key>{cfg['ipsec']['psk']}</key></pre-shared-key></authentication>
        <protocol>
          <ikev2>
            <ike-crypto-profile>{cfg['ipsec']['ike_crypto_profile']}</ike-crypto-profile>
            <dpd><enable>yes</enable></dpd>
          </ikev2>
          <version>ikev2</version>
        </protocol>
        <local-address><interface>{cfg['paloalto']['wan_interface']}</interface></local-address>
        <peer-address><ip>{cfg['fortigate']['wan_ip']}</ip></peer-address>
        """
        self._set_config(xpath, element)
        print(f"[Palo Alto] IKE Gateway '{cfg['ipsec']['ike_gateway']}' configurado.")

    def configure_ipsec_tunnel(self) -> None:
        cfg = VPN_CONFIG
        # Route-based: sem proxy IDs — o BGP gerencia o roteamento pelo túnel
        xpath = f"/config/devices/entry[@name='localhost.localdomain']/network/tunnel/ipsec/entry[@name='{cfg['ipsec']['tunnel_name']}']"
        element = f"""
        <tunnel-interface>{cfg['paloalto']['tunnel_interface']}</tunnel-interface>
        <ike>
          <gateway><entry name="{cfg['ipsec']['ike_gateway']}"/></gateway>
          <ipsec-crypto-profile>{cfg['ipsec']['ipsec_crypto_profile']}</ipsec-crypto-profile>
        </ike>
        """
        self._set_config(xpath, element)
        print(f"[Palo Alto] IPSec Tunnel '{cfg['ipsec']['tunnel_name']}' configurado (route-based, sem proxy IDs).")

    def configure_tunnel_ip(self) -> None:
        cfg = VPN_CONFIG
        xpath = f"/config/devices/entry[@name='localhost.localdomain']/network/interface/tunnel/units/entry[@name='{cfg['paloalto']['tunnel_interface']}']"
        element = f"""
        <ip><entry name="{cfg['paloalto']['tunnel_ip']}"/></ip>
        """
        self._set_config(xpath, element)
        print(f"[Palo Alto] IP do túnel configurado: {cfg['paloalto']['tunnel_ip']}.")

    def configure_bgp(self) -> None:
        cfg = VPN_CONFIG
        bgp = cfg["bgp"]
        xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='default']/protocol/bgp"
        element = f"""
        <enable>yes</enable>
        <router-id>{bgp['router_id']}</router-id>
        <local-as>{bgp['local_as']}</local-as>
        <peer-group>
          <entry name="VPN-PEERS">
            <type><ebgp><remove-private-as>yes</remove-private-as></ebgp></type>
            <peer>
              <entry name="FORTIGATE">
                <enable>yes</enable>
                <peer-address><ip>{bgp['neighbor_ip']}</ip></peer-address>
                <peer-as>{bgp['neighbor_as']}</peer-as>
                <local-address>
                  <interface>{cfg['paloalto']['tunnel_interface']}</interface>
                  <ip>{cfg['paloalto']['tunnel_ip']}</ip>
                </local-address>
              </entry>
            </peer>
          </entry>
        </peer-group>
        <redistribution-profile>
          <entry name="CONNECTED">
            <action><redist>yes</redist></action>
            <filter><type><connected/></type></filter>
            <priority>1</priority>
          </entry>
        </redistribution-profile>
        """
        self._set_config(xpath, element)
        print(f"[Palo Alto] BGP AS {bgp['local_as']} configurado — peer {bgp['neighbor_ip']} AS {bgp['neighbor_as']}.")

    def configure_security_policy(self) -> None:
        cfg = VPN_CONFIG
        xpath = "/config/devices/entry[@name='localhost.localdomain']/vsys/entry[@name='vsys1']/rulebase/security/rules/entry[@name='LAN-to-FG-VPN']"
        element = f"""
        <from><member>{cfg['paloalto']['zone_trust']}</member></from>
        <to><member>{cfg['paloalto']['zone_vpn']}</member></to>
        <source><member>any</member></source>
        <destination><member>any</member></destination>
        <application><member>any</member></application>
        <service><member>application-default</member></service>
        <action>allow</action>
        """
        self._set_config(xpath, element)
        print("[Palo Alto] Security policy criada.")

    def validate(self) -> bool:
        root = self._op("<show><vpn><ipsec-sa></ipsec-sa></vpn></show>")
        entries = root.findall(".//entry")
        tunnel_name = VPN_CONFIG["ipsec"]["tunnel_name"]
        for entry in entries:
            name = entry.findtext("name") or ""
            if tunnel_name in name:
                state = entry.findtext("state") or "unknown"
                if state in ("active", "init"):
                    print(f"[Palo Alto] Túnel '{tunnel_name}' ativo (estado: {state}).")
                    return True
                else:
                    print(f"[ALERTA][Palo Alto] Túnel '{tunnel_name}' com estado inesperado: {state}.")
                    return False
        print(f"[ALERTA][Palo Alto] Túnel '{tunnel_name}' não encontrado nas SAs ativas.")
        return False


def main() -> None:
    pa = PaloAltoVPN(PALOALTO_MGMT, PALOALTO_USER, PALOALTO_PASS)

    print("=== Configurando VPN no Palo Alto ===")
    pa.configure_ike_crypto_profile()
    pa.configure_ipsec_crypto_profile()
    pa.configure_ike_gateway()
    pa.configure_ipsec_tunnel()
    pa.configure_tunnel_ip()
    pa.configure_bgp()
    pa.configure_security_policy()
    pa.commit()

    print("\n=== Validando túnel ===")
    ok = pa.validate()
    if not ok:
        print("[ALERTA] Verifique os logs: show log system direction equal forward")


if __name__ == "__main__":
    main()
