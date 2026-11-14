
from flask import Flask, render_template, jsonify
import mysql.connector
from datetime import datetime
import requests
import threading
import time

app = Flask(__name__)

# ----------------------------------------------------
# Service-Status prüfen (KitchenOwl, Portainer, PiHole)
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

LOADPOINT_ID = 1

# True = Sommerlogik aktiv
# False = Keine Eingriffe in EVCC
USE_BATTERY_RULES = False

# Status alle 60 Sekunden prüfen
CHECK_INTERVAL = 60

# True = Nur Entscheidungen anzeigen
# False = Schaltbefehle senden
DRY_RUN = False

session = requests.Session()


# ==========================================
# EVCC STATUS AUSLESEN
# ==========================================
def get_evcc_state():

    try:
        response = session.get(
            f"{EVCC_URL}/api/state",
            timeout=5
        )

        response.raise_for_status()

        data = response.json()
        data = data.get("result", data)

        battery = data["battery"]

        loadpoint = data["loadpoints"][
            LOADPOINT_ID - 1
        ]

        return {
            "soc": float(battery["soc"]),
            "mode": loadpoint["mode"],
            "always_charge": loadpoint["alwaysCharge"]
        }

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        IndexError,
        TypeError
    ) as error:

        print(
            "Fehler beim Lesen des EVCC-Status:",
            error
        )

        return None


# ==========================================
# API BEFEHL SENDEN
# ==========================================
def send_command(path):

    url = f"{EVCC_URL}{path}"

    if DRY_RUN:
        print(f"TESTMODUS: POST {path}")
        return True

    try:
        response = session.post(
            url,
            timeout=5
        )

        response.raise_for_status()

        return True

    except requests.RequestException as error:

        print("Fehler beim Schalten:", error)

        return False


# ==========================================
# LADEPUNKT SCHALTEN
# ==========================================
def set_loadpoint(enabled, state):

    current_mode = state["mode"]
    always_charge = state["always_charge"]

    if enabled:

        if always_charge != "on":

            if not send_command(
                f"/api/loadpoints/{LOADPOINT_ID}"
                "/alwayscharge/on"
            ):
                return

        if current_mode != "smart":

            if not send_command(
                f"/api/loadpoints/{LOADPOINT_ID}"
                "/mode/smart"
            ):
                return

        if (
            current_mode != "smart"
            or always_charge != "on"
        ):
            print(
                f"{datetime.now():%H:%M:%S}"
                " -> MIN+PV EIN"
            )

    else:

        if current_mode != "off":

            if send_command(
                f"/api/loadpoints/{LOADPOINT_ID}"
                "/mode/off"
            ):

                print(
                    f"{datetime.now():%H:%M:%S}"
                    " -> LADEN AUS"
                )


# ==========================================
# HAUPTSCHLEIFE EVCC
# ==========================================
def evcc_control_loop():

    print("EVCC Ladeautomatik gestartet")
    print("Batterieregeln:", USE_BATTERY_RULES)
    print("Testmodus:", DRY_RUN)

    while True:

        if not USE_BATTERY_RULES:

            print(
                f"{datetime.now():%H:%M:%S}"
                " | Automatik deaktiviert"
            )

            time.sleep(CHECK_INTERVAL)
            continue

        state = get_evcc_state()

        if state is None:

            time.sleep(CHECK_INTERVAL)
            continue

        soc = state["soc"]
        mode = state["mode"]

        now = datetime.now()

        print(
            f"{now:%H:%M:%S} | "
            f"Akku: {soc:.1f}% | "
            f"Modus: {mode} | "
            f"Min+PV: {state['always_charge']}"
        )

        # 19:00 - 09:00
        # Immer AUS
        if now.hour >= 19 or now.hour < 9:

            set_loadpoint(False, state)

        # 09:00 - 12:00
        # EIN ab 20 %
        # AUS unter 15 %
        elif 9 <= now.hour < 12:

            if soc >= 20:
                set_loadpoint(True, state)

            elif soc < 15:
                set_loadpoint(False, state)

        # 12:00 - 19:00
        # EIN ab 85 %
        # AUS unter 75 %
        else:

            if soc >= 85:
                set_loadpoint(True, state)

            elif soc < 75:
                set_loadpoint(False, state)

        time.sleep(CHECK_INTERVAL)


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

    string_aliases = [
        "Cheapest_Name",
        "WetterStatusAktuell"
    ]

    number_aliases = [
        "SolarSOC",
        "TemperaturMomentan",
        "PV_Ost",
        "PV_West",
        "Cheapest_Diesel"
    ]

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

    startpage["TemperaturMomentan"] = temp_data.get(
        "TemperaturMomentan"
    )

    startpage["PV_gesamt"] = round(
        (pv_ost + pv_west) / 1000.0, 3
    )

    startpage["PV_Ost"] = round(pv_ost / 1000.0, 3)
    startpage["PV_West"] = round(pv_west / 1000.0, 3)

    startpage["Cheapest_Diesel"] = temp_data.get(
        "Cheapest_Diesel"
    )

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

            if (
                "Sonnenaufgang" in alias
                or "Sonnenuntergang" in alias
            ):

                try:
                    ts = int(val) / 1000
                    val = datetime.fromtimestamp(
                        ts
                    ).strftime("%H:%M")

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
        "BFT_Rösrath_E5",
        "BFT_Rösrath_E10",
        "BFT_Rösrath_Diesel",
        "JET_E5",
        "JET_E10",
        "JET_Diesel",
        "Total_E5",
        "Total_E10",
        "Total_Diesel",
        "BFT_Hoffnungsthal_E5",
        "BFT_Hoffnungsthal_E10",
        "BFT_Hoffnungsthal_Diesel",
        "Mundorf_E5",
        "Mundorf_E10",
        "Mundorf_Diesel",
        "Roth_E5",
        "Roth_Diesel",
        "Roth_E10"
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
            prices[alias] = {
                "preis": row["val"]
            }

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

    aliases = [
        "SolarSOC",
        "PV_Ost",
        "PV_West",
        "EnergiebedarfHaus"
    ]

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

            solar[alias] = {
                "wert": val
            }

    cursor.close()
    conn.close()

    return solar


# ----------------------------------------------------
# Sensoren und zusätzliche Anlagendaten
# ----------------------------------------------------
def get_sensordaten():

    conn = mysql.connector.connect(
        host="",
        user="",
        password="",
        database=""
    )

    cursor = conn.cursor(dictionary=True)

    # Numerische Werte
    number_aliases = [

        # Bestehende Sensoren
        "TemperaturSchuppen",
        "TemperaturWohnzimmer",
        "LuftfeuchtigkeitWohnzimmer",
        "LuftdruckWohnzimmer",

        # Wärmepumpe
        "AußentemperaturWärmepumpe",
        "StartsWärmepumpe",
        "StundenLaufzeitWärmepumpe",
        "TemperaturWasser",

        # Waschkeller
        "LuftdruckWaschkeller",
        "LuftfeuchtigkeitWaschkeller",
        "TemperaturWaschkeller",

        # Terrasse
        "TemperaturTerasse",

        # BMW
        "BMW_VerbleinderTank"
    ]

    # String-Werte
    string_aliases = [

        # Bestehende Sensoren
        "SensorStatusSchuppen",
        "SensorStatusWohnzimmer",

        # Neue Sensorstatus
        "SensorStatusWaschkeller",
        "StatusSensorTerasse"
    ]

    sensoren = {}

    # Numerische Sensorwerte abfragen
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
            sensoren[alias] = row["val"]

    # Statuswerte abfragen
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
            sensoren[alias] = row["val"]

    cursor.close()
    conn.close()

    return sensoren


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
        startpage=get_startpage_data(),
        sensoren=get_sensordaten()
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


@app.route('/api/sensoren')
def api_sensoren():

    return jsonify(get_sensordaten())


@app.route('/api/scriptable')
def api_scriptable():
    """JSON-Schnittstelle für Scriptable."""

    startpage = get_startpage_data()
    solar = get_solar()
    sensoren = get_sensordaten()

    def solar_wert(alias):

        eintrag = solar.get(alias)

        return (
            eintrag.get("wert")
            if isinstance(eintrag, dict)
            else None
        )

    return jsonify({

        "WetterStatusAktuell":
            startpage.get("WetterStatusAktuell"),

        "batterie_soc_prozent":
            startpage.get("SolarSOC"),

        "pv_gesamt_kw":
            startpage.get("PV_gesamt"),

        "pv_ost_kw":
            solar_wert("PV_Ost"),

        "pv_west_kw":
            solar_wert("PV_West"),

        "hausverbrauch_kw":
            solar_wert("EnergiebedarfHaus"),

        "sensoren":
            sensoren,

        "aktualisiert":
            datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
    })


# ----------------------------------------------------
# Programmstart
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
