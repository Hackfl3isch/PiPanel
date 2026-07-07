from flask import Flask, render_template, jsonify
import mysql.connector
from datetime import datetime
import requests   # <<< NEU
import threading
import time

app = Flask(__name__)

# ----------------------------------------------------
# Service-Status prüfen (KitchenOwl & Portainer)
# ----------------------------------------------------
def check_services():
    services = {
        "KitchenOwl": "http://192.168.178.118:32768/signin",
        "Portainer": "http://192.168.178.118:9000/#!/auth",
	"PiHole": "http://192.168.178.33/admin/login"
    }

    status = {}

    for name, url in services.items():
        try:
            r = requests.get(url, timeout=3)
            status[name] = {
                "url": url,
                "online": r.status_code < 500,
                "code": r.status_code
            }
        except requests.exceptions.RequestException:
            status[name] = {
                "url": url,
                "online": False,
                "code": None
            }

    return status

# ----------------------------------------------------
# EVCC Ladepunkt steuern
# ----------------------------------------------------

EVCC_URL = "http://192.168.178.118:7070"

# True = Sommerlogik aktiv
# False = Akku-Regeln komplett deaktivieren
USE_BATTERY_RULES = True
last_mode = None


def get_evcc_battery_soc():
    """
    Batteriestand aus EVCC lesen.
    """
    try:
        r = requests.get(f"{EVCC_URL}/api/state", timeout=5)
        r.raise_for_status()

        data = r.json()

        return float(data["battery"]["soc"])

    except Exception as e:
        print("EVCC Batteriestand konnte nicht gelesen werden:", e)
        return None


def set_loadpoint(enabled):
    """
    Ladepunkt auf minpv oder off schalten.
    """
    global last_mode

    mode = "minpv" if enabled else "off"

    # Nur schalten wenn sich etwas geändert hat
    if mode == last_mode:
        return

    try:
        r = requests.post(
            f"{EVCC_URL}/api/loadpoints/1/mode/{mode}",
            timeout=5
        )

        r.raise_for_status()

        last_mode = mode

        print(f"{datetime.now():%H:%M:%S} -> Ladepunkt auf {mode}")

    except Exception as e:
        print("Fehler beim Schalten:", e)


def evcc_control_loop():
    """
    Prüft jede Minute Uhrzeit und Batteriespeicher.
    """

    while True:

        now = datetime.now()

        # --------------------------------------------------
        # Nachts niemals laden (22:00 - 09:00)
        # --------------------------------------------------
        if now.hour >= 22 or now.hour < 9:
            set_loadpoint(False)

        # --------------------------------------------------
        # Zwischen 09:00 und 12:00 immer laden
        # (unabhängig vom Batteriespeicher)
        # --------------------------------------------------
        elif 9 <= now.hour < 12:

            soc = get_evcc_battery_soc()

            if soc is not None:

                print(f"Batterie: {soc:.1f}%")

                # Einschalten erst ab 20 %
                if soc >= 20:
                    set_loadpoint(True)

                # Ausschalten unter 15 %
                elif soc < 15:
                    set_loadpoint(False)

        # --------------------------------------------------
        # Akku-Regeln deaktiviert
        # --------------------------------------------------
        elif not USE_BATTERY_RULES:
            set_loadpoint(True)

        # --------------------------------------------------
        # Akku-Regeln aktiv
        # --------------------------------------------------
        else:

            soc = get_evcc_battery_soc()

            if soc is not None:

                print(f"Batterie: {soc:.1f}%")

                if soc >= 95:
                    set_loadpoint(True)
                elif soc < 70:
                    set_loadpoint(False)

        time.sleep(60)
# ----------------------------------------------------
# Startpage-Daten
# ----------------------------------------------------

def get_startpage_data():
    conn = mysql.connector.connect(
        host="",
        user="",
        password="",
        database=""
    )
    cursor = conn.cursor(dictionary=True)

    string_aliases = ["Cheapest_Name", "WetterStatusAktuell"]
    number_aliases = ["SolarSOC","TemperaturMomentan", "PV_Ost", "PV_West","Cheapest_Diesel"]

    startpage = {}

    query_str = """
        SELECT t.val
        FROM ts_string t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name = %s
        ORDER BY t.Datum DESC
        LIMIT 1
    """
    for alias in string_aliases:
        cursor.execute(query_str, (alias,))
        row = cursor.fetchone()
        if row:
            startpage[alias] = row["val"]

    query_num = """
        SELECT t.val
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name = %s
        ORDER BY t.Datum DESC
        LIMIT 1
    """
    temp_data = {}
    for alias in number_aliases:
        cursor.execute(query_num, (alias,))
        row = cursor.fetchone()
        if row:
            temp_data[alias] = row["val"]

    pv_ost = temp_data.get("PV_Ost", 0)
    pv_west = temp_data.get("PV_West", 0)

    startpage["TemperaturMomentan"] = temp_data.get("TemperaturMomentan")
    startpage["PV_gesamt"] = round((pv_ost + pv_west) / 1000.0, 3)
    startpage["PV_Ost"] = round(pv_ost / 1000.0, 3)
    startpage["PV_West"] = round(pv_west / 1000.0, 3)
    startpage["Cheapest_Diesel"] = temp_data.get("Cheapest_Diesel")
    startpage["SolarSOC"] = temp_data.get("SolarSOC")

    cursor.close()
    conn.close()
    return startpage


# ----------------------------------------------------
# Wetter
# ----------------------------------------------------
def get_wetter():
    conn = mysql.connector.connect(
        host="",
        user="",
        password="",
        database=""
    )
    cursor = conn.cursor(dictionary=True)

    number_aliases = [
        "TemperaturMomentan",
        "TemperaturMinimalHeute",
        "TemperaturMaximalHeute",
        "TemperaturMinimalMorgen",
        "TemperaturMaximalMorgen"
    ]

    string_aliases = [
        "SonnenaufgangHeute",
        "SonnenuntergangHeute",
        "WetterStatusAktuell",
        "SonnenaufgangMorgen",
        "SonnenuntergangMorgen"
    ]

    wetter = {}

    query_num = """
        SELECT t.val
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name = %s
        ORDER BY t.Datum DESC
        LIMIT 1
    """
    for alias in number_aliases:
        cursor.execute(query_num, (alias,))
        row = cursor.fetchone()
        if row:
            wetter[alias] = row["val"]

    query_str = """
        SELECT t.val
        FROM ts_string t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name = %s
        ORDER BY t.Datum DESC
        LIMIT 1
    """
    for alias in string_aliases:
        cursor.execute(query_str, (alias,))
        row = cursor.fetchone()
        if row:
            val = row["val"]
            if "Sonnenaufgang" in alias or "Sonnenuntergang" in alias:
                try:
                    ts = int(val) / 1000
                    val = datetime.fromtimestamp(ts).strftime("%H:%M")
                except:
                    pass
            wetter[alias] = val

    cursor.close()
    conn.close()
    return wetter


# ----------------------------------------------------
# Spritpreise
# ----------------------------------------------------
def get_spritpreise():
    conn = mysql.connector.connect(
        host="",
        user="",
        password="",
        database=""
    )
    cursor = conn.cursor(dictionary=True)

    aliases = [
        "BFT_Rösrath_E5","BFT_Rösrath_E10","BFT_Rösrath_Diesel",
        "JET_E5","JET_E10","JET_Diesel",
        "Total_E5","Total_E10","Total_Diesel",
        "BFT_Hoffnungsthal_E5","BFT_Hoffnungsthal_E10","BFT_Hoffnungsthal_Diesel",
        "Mundorf_E5","Mundorf_E10","Mundorf_Diesel","Roth_E5","Roth_Diesel","Roth_E10"
    ]

    prices = {}
    query = """
        SELECT t.val
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name = %s
        ORDER BY t.Datum DESC
        LIMIT 1
    """
    for alias in aliases:
        cursor.execute(query, (alias,))
        row = cursor.fetchone()
        if row:
            prices[alias] = {"preis": row["val"]}

    cursor.close()
    conn.close()
    return prices


# ----------------------------------------------------
# Solar
# ----------------------------------------------------
def get_solar():
    conn = mysql.connector.connect(
        host="",
        user="",
        password="",
        database=""
    )
    cursor = conn.cursor(dictionary=True)

    aliases = ["SolarSOC", "PV_Ost", "PV_West","EnergiebedarfHaus"]
    solar = {}

    query = """
        SELECT t.val
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name = %s
        ORDER BY t.Datum DESC
        LIMIT 1
    """
    for alias in aliases:
        cursor.execute(query, (alias,))
        row = cursor.fetchone()
        if row:
            val = row["val"]
            if alias != "SolarSOC":
                val = round(val / 1000.0, 3)
            solar[alias] = {"wert": val}

    cursor.close()
    conn.close()
    return solar


# ----------------------------------------------------
# Routes
# ----------------------------------------------------
@app.route('/')
def index():
    return render_template(
        "index.html",
        wetter=get_wetter(),
        sprit=get_spritpreise(),
        solar=get_solar(),
        startpage=get_startpage_data()
    )


@app.route('/api/startpage')
def api_startpage():
    return jsonify(get_startpage_data())


@app.route('/api/wetter')
def api_wetter():
    return jsonify(get_wetter())


@app.route('/api/sprit')
def api_sprit():
    return jsonify(get_spritpreise())


@app.route('/api/solar')
def api_solar():
    return jsonify(get_solar())


@app.route('/api/services')
def api_services():
    return jsonify(check_services())


# ----------------------------------------------------
if __name__ == '__main__':

    thread = threading.Thread(
        target=evcc_control_loop,
        daemon=True
    )
    thread.start()

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )


