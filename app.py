from flask import Flask, render_template, jsonify
import mysql.connector
from datetime import datetime
import requests   # <<< NEU

app = Flask(__name__)

# ----------------------------------------------------
# Service-Status prüfen (KitchenOwl & Portainer)
# ----------------------------------------------------
def check_services():
    services = {
        "KitchenOwl": "http://192.168.178.118:32768/signin",
        "Portainer": "http://192.168.178.118:9000/#!/auth"
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



# --- Funktion: Wetterdaten abrufen ---
def get_wetter():
    conn = mysql.connector.connect(

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


    # Zahlenwerte: pro Alias nur den neuesten Wert
    query_num = """
        SELECT t.val, t.Datum
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

    # Stringwerte: pro Alias nur den neuesten Wert
    query_str = """
        SELECT t.val, t.Datum
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
            # Sonnenaufgang/Sonnenuntergang in HH:MM umwandeln
            if alias in ["SonnenaufgangHeute", "SonnenuntergangHeute"]:
                try:
                    ts = int(val) / 1000  # Millisekunden → Sekunden
                    val = datetime.fromtimestamp(ts).strftime("%H:%M")
                except Exception:
                    pass
            wetter[alias] = val

    cursor.close()
    conn.close()
    return wetter

# --- Funktion: Spritpreise abrufen ---
def get_spritpreise():
    conn = mysql.connector.connect(

    )
    cursor = conn.cursor(dictionary=True)

    aliases = [
        "BFT_Rösrath_E5","BFT_Rösrath_E10","BFT_Rösrath_Diesel",
        "JET_E5","JET_E10","JET_Diesel",
        "Total_E5","Total_E10","Total_Diesel",
        "BFT_Hoffnungsthal_E5","BFT_Hoffnungsthal_E10","BFT_Hoffnungsthal_Diesel",
        "Mundorf_E5","Mundorf_E10","Mundorf_Diesel"
    ]

    latest_prices = {}
    query = """
        SELECT t.val, t.Datum
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
            latest_prices[alias] = {"preis": row["val"], "datum": row["Datum"]}

    cursor.close()
    conn.close()
    return latest_prices

# --- Funktion: Solarwerte abrufen ---
def get_solar():
    conn = mysql.connector.connect(

    )
    cursor = conn.cursor(dictionary=True)

    aliases = ["SolarSOC", "PV_Ost", "PV_West"]

    latest_solar = {}
    query = """
        SELECT t.val, t.Datum
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
            latest_solar[alias] = {"wert": row["val"], "datum": row["Datum"]}

    cursor.close()
    conn.close()
    return latest_solar

# --- Routes ---
@app.route('/')
def index():
    wetter = get_wetter()
    spritpreise = get_spritpreise()
    solar = get_solar()
    return render_template("index.html", wetter=wetter, sprit=spritpreise, solar=solar)

@app.route('/api/wetter')
def api_wetter():
    return jsonify(get_wetter())

@app.route('/api/sprit')
def api_sprit():
    return jsonify(get_spritpreise())

@app.route('/api/solar')
def api_solar():
    return jsonify(get_solar())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
