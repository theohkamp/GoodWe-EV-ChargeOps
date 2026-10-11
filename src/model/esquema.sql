-- EV ChargeOps - esquema do banco de dados (SQLite)
-- As seis tabelas definidas na Sprint 1, com os mesmos nomes de campos,
-- mais a tabela com o export diario do SEMS Portal.
-- PRIMARY KEY identifica cada registro; REFERENCES liga uma tabela a outra.

CREATE TABLE IF NOT EXISTS units (
    id     INTEGER PRIMARY KEY,
    name   TEXT    NOT NULL,
    block  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY,
    unit_id  INTEGER NOT NULL REFERENCES units (id),
    name     TEXT    NOT NULL,
    email    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS rfid_cards (
    uid      TEXT    PRIMARY KEY,
    user_id  INTEGER NOT NULL REFERENCES users (id),
    status   BOOLEAN NOT NULL                 -- 1 = ativo, 0 = bloqueado
);

CREATE TABLE IF NOT EXISTS chargers (
    id            TEXT PRIMARY KEY,
    model         TEXT NOT NULL,
    max_power_kw  REAL NOT NULL,
    location      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY,
    rfid_uid       TEXT    NOT NULL REFERENCES rfid_cards (uid),
    charger_id     TEXT    NOT NULL REFERENCES chargers (id),
    start_time     TEXT    NOT NULL,          -- "AAAA-MM-DD HH:MM"
    end_time       TEXT    NOT NULL,
    kwh_delivered  REAL    NOT NULL,
    -- campos extras em relacao ao esquema da Sprint 1
    potencia_media_kw  REAL    NOT NULL,
    pico_kw            REAL    NOT NULL,
    interrompida       BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id           INTEGER PRIMARY KEY,
    unit_id      INTEGER NOT NULL REFERENCES units (id),
    month        TEXT    NOT NULL,            -- "MM-AAAA"
    total_kwh    REAL    NOT NULL,
    total_value  REAL    NOT NULL,
    status       TEXT    NOT NULL,            -- PENDING, PAID ou ISENTO
    -- campos extras: guardam os valores usados no fechamento, para a auditoria
    tarifa       REAL    NOT NULL,
    taxa_admin   REAL    NOT NULL,
    sessoes      INTEGER NOT NULL,
    fechado_em   TEXT    NOT NULL,
    vencimento   TEXT    NOT NULL,
    pago_em      TEXT    NOT NULL,
    UNIQUE (unit_id, month)                   -- uma fatura por unidade em cada mes
);

CREATE TABLE IF NOT EXISTS sems_export (
    data             TEXT NOT NULL,           -- "AAAA-MM-DD"
    charger_id       TEXT NOT NULL REFERENCES chargers (id),
    energia_dia_kwh  REAL NOT NULL,
    PRIMARY KEY (data, charger_id)
);
