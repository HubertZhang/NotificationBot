CREATE TABLE IF NOT EXISTS "user"
(
    user_id INT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT,
    start_time INT
, time_setting TEXT NULL);
CREATE TABLE IF NOT EXISTS "hack_record"
(
    user_id INT,
    time INT,
    CONSTRAINT hack_record_user_user_id_fk FOREIGN KEY (user_id) REFERENCES user (user_id)
);
CREATE VIEW latest_hack as SELECT user_id, max(time) as latest_hack_time FROM main.hack_record GROUP BY user_id;
