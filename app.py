from flask import Flask, render_template 
import mysql.connector
from datetime import datetime
from flask import jsonify

app = Flask(__name__)

# --- Funktion: Wetterdaten abrufen ---
def get_wetter():
    conn = mysql.connector.connect(
        host=,
        user=,
        password=,
        database=    )
    cursor = conn.cursor(dictionary=True)

    # --- Aliase definieren ---
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
        "WetterStatusAktuell"
    ]

    wetter = {}

    # --- Zahlenwerte abfragen ---
    query_num = f"""
        SELECT d.name, t.val, t.Datum
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name IN ({','.join(['%s']*len(number_aliases))})
        ORDER BY t.Datum DESC
    """
    cursor.execute(query_num, tuple(number_aliases))
    rows = cursor.fetchall()
    for row in rows:
        alias = row["name"]
        if alias not in wetter:  # nur neuesten Wert nehmen
            wetter[alias] = row["val"]

    # --- Stringwerte abfragen ---
    query_str = f"""
        SELECT d.name, t.val, t.Datum
        FROM ts_string t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name IN ({','.join(['%s']*len(string_aliases))})
        ORDER BY t.Datum DESC
    """
    cursor.execute(query_str, tuple(string_aliases))
    rows = cursor.fetchall()
    for row in rows:
        alias = row["name"]
        val = row["val"]

        # Sonderfall: Sonnenaufgang / Sonnenuntergang
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
        host=,
        user=,
        password=,
        database=
    )
    cursor = conn.cursor(dictionary=True)

    # Liste der Aliase, die dich interessieren
    aliases = [
        "BFT_Rösrath_E5",
        "BFT_Rösrath_E10",
        "BFT_Rösrath_diesel",
        "JET_E5",
        "JET_E10",
        "JET_diesel",
        "Total_E5",
        "Total_E10",
        "Total_Diesel",
        "BFT_Hoffnungsthal_E5",
        "BFT_Hoffnungsthal_E10",
        "BFT_Hoffnungsthal_diesel",
        "Mundorf_E5",
        "Mundorf_E10",
        "Mundorf_diesel"
    ]

    # Query für alle Aliase auf einmal
    query = f"""
        SELECT d.name, t.val, t.Datum
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name IN ({','.join(['%s']*len(aliases))})
        ORDER BY t.Datum DESC
    """
    cursor.execute(query, tuple(aliases))
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    # Jetzt das Ergebnis aufbereiten: pro Alias nur der neueste Wert
    latest_prices = {}
    for row in rows:
        alias = row["name"]
        if alias not in latest_prices:  # nur das erste (neueste) nehmen
            latest_prices[alias] = {
                "preis": row["val"],
                "datum": row["Datum"]
            }

    return latest_prices
def get_solar():
    conn = mysql.connector.connect(
        host=,
        user=,
        password=,
        database=
    )
    cursor = conn.cursor(dictionary=True)

    aliases = ["SolarSOC", "PV_Ost", "PV_West"]

    query = f"""
        SELECT d.name, t.val, t.Datum
        FROM ts_number t
        JOIN datapoints d ON t.id = d.id
        WHERE d.name IN ({','.join(['%s']*len(aliases))})
        ORDER BY t.Datum DESC
    """
    cursor.execute(query, tuple(aliases))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    latest_solar = {}
    for row in rows:
        alias = row["name"]
        if alias not in latest_solar:
            latest_solar[alias] = {
                "wert": row["val"],
                "datum": row["Datum"]
            }

    return latest_solar
# --- Route: Startseite ---
@app.route('/api/solar')
def api_solar():
    data = get_solar()
    return jsonify(data)

# --- Route: Startseite ---
@app.route('/')
def index():
    wetter = get_wetter()
    spritpreise = get_spritpreise()
    solar = get_solar()
    return render_template("index.html", wetter=wetter, sprit=spritpreise, solar=solar)


@app.route('/api/wetter')
def api_wetter():
    wetter = get_wetter()
    return jsonify(wetter)

@app.route('/api/sprit')
def api_sprit():
    sprit = get_spritpreise()
    return jsonify(sprit)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

