import os
import datetime
import psycopg2


def log_row(db_url: str, drone_id: str, lat: float | None, lon: float | None, batt_v: float | None, ai_conf: float | None):
    conn = psycopg2.connect(db_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO flight_log (time, drone_id, latitude, longitude, battery_voltage, ai_decision_confidence) VALUES (%s,%s,%s,%s,%s,%s)",
                (datetime.datetime.utcnow(), drone_id, lat, lon, batt_v, ai_conf)
            )
    finally:
        conn.close()


if __name__ == "__main__":
    # smoke test
    url = os.environ.get("DATABASE_URL", "postgresql://lesnar:lesnar@127.0.0.1:5432/lesnar")
    log_row(url, "DRONE-001", None, None, 11.8, 0.92)