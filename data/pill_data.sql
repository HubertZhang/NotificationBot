CREATE TABLE pill_record
(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    alarm_time INTEGER,
    description TEXT
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE user
(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT
);
CREATE UNIQUE INDEX user_user_id_uindex ON user (user_id);
