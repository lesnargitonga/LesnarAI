CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS flight_log (
  time TIMESTAMPTZ NOT NULL,
  drone_id TEXT NOT NULL,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  battery_voltage DOUBLE PRECISION,
  ai_decision_confidence DOUBLE PRECISION
);

SELECT create_hypertable('flight_log', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS flight_log_time_idx ON flight_log (time DESC);