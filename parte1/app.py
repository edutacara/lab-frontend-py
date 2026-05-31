from flask import Flask, render_template, request, jsonify
from cisco_switch import CiscoSwitch

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/vlan")
def vlan():
    return render_template("vlan.html")


@app.route("/hostname")
def hostname():
    return render_template("hostname.html")


@app.route("/save")
def save():
    return render_template("save.html")


@app.route("/backup")
def backup():
    return render_template("backup.html")


def get_switch(data):
    return CiscoSwitch(
        host=data.get("host", "").strip(),
        username=data.get("username", "").strip(),
        password=data.get("password", ""),
        port=int(data.get("port", 22)),
        secret=data.get("secret", ""),
    )


@app.route("/api/configure-vlans", methods=["POST"])
def api_configure_vlans():
    data = request.get_json()
    vlans = data.get("vlans", [])
    if not vlans:
        return jsonify({"success": False, "message": "Nenhuma VLAN informada."})
    switch = get_switch(data)
    try:
        switch.connect()
        switch.configure_vlans(vlans)
        alerts = switch.validate_config(vlans, expected_hostname=None)
        return jsonify({"success": True, "message": "VLANs configuradas com sucesso!", "alerts": alerts})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        switch.disconnect()


@app.route("/api/configure-hostname", methods=["POST"])
def api_configure_hostname():
    data = request.get_json()
    hostname = data.get("hostname", "").strip()
    if not hostname:
        return jsonify({"success": False, "message": "Hostname não informado."})
    switch = get_switch(data)
    try:
        switch.connect()
        switch.configure_hostname(hostname)
        alerts = switch.validate_config(expected_vlans=[], expected_hostname=hostname)
        return jsonify({"success": True, "message": "Hostname configurado com sucesso!", "alerts": alerts})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        switch.disconnect()


@app.route("/api/save-config", methods=["POST"])
def api_save_config():
    data = request.get_json()
    switch = get_switch(data)
    try:
        switch.connect()
        switch.save_config()
        return jsonify({"success": True, "message": "Configuração salva na NVRAM com sucesso!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        switch.disconnect()


@app.route("/api/backup", methods=["POST"])
def api_backup():
    data = request.get_json()
    switch = get_switch(data)
    try:
        switch.connect()
        backup_file = switch.backup_config()
        return jsonify({"success": True, "message": "Backup realizado com sucesso!", "backup_file": backup_file})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        switch.disconnect()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
