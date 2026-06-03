from netmiko import ConnectHandler
from datetime import datetime
import unicodedata
import os


def _ascii_safe(name: str) -> str:
    """Normalize VLAN names to ASCII — Cisco IOS rejects non-ASCII characters."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")


class CiscoSwitch:
    def __init__(self, host, username, password, port=22, secret=""):
        self.device = {
            "device_type": "cisco_ios",
            "host": host,
            "username": username,
            "password": password,
            "port": port,
            "secret": secret,
        }
        self.connection = None

    def connect(self):
        self.connection = ConnectHandler(**self.device)
        if self.device["secret"]:
            self.connection.enable()

    def disconnect(self):
        if self.connection:
            self.connection.disconnect()

    def configure_hostname(self, hostname):
        self.connection.send_config_set([f"hostname {hostname}"])

    def configure_vlans(self, vlans):
        commands = []
        for vlan in vlans:
            safe_name = _ascii_safe(vlan["name"])
            commands += [f"vlan {vlan['id']}", f"name {safe_name}", "exit"]
        self.connection.send_config_set(commands)

    def save_config(self):
        self.connection.send_command(
            "write memory", expect_string=r"#", read_timeout=30
        )

    def backup_config(self, backup_dir="backups"):
        os.makedirs(backup_dir, exist_ok=True)
        prompt = self.connection.find_prompt()
        hostname = prompt.strip("#>").strip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(backup_dir, f"{hostname}_{timestamp}.txt")
        config = self.connection.send_command("show running-config")
        with open(filename, "w") as f:
            f.write(config)
        return filename

    def validate_config(self, expected_vlans, expected_hostname):
        alerts = []

        if expected_hostname:
            current_hostname = self.connection.find_prompt().strip("#>").strip()
            if current_hostname != expected_hostname:
                alerts.append(
                    f"Hostname atual '{current_hostname}' diverge do esperado '{expected_hostname}'"
                )

        if expected_vlans:
            vlan_output = self.connection.send_command("show vlan brief")
            for vlan in expected_vlans:
                vlan_id = str(vlan["id"])
                vlan_name = vlan["name"]
                if vlan_id not in vlan_output:
                    alerts.append(f"VLAN {vlan_id} não encontrada no switch")
                elif vlan_name not in vlan_output:
                    alerts.append(
                        f"VLAN {vlan_id} existe mas o nome '{vlan_name}' está diferente"
                    )

        return alerts
