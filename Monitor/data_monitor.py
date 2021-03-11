import math
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import time
import traceback
import logging
import sys
try:
    from w1thermsensor import W1ThermSensor
except ImportError:
    logging.error("Could not find w1thermsensor library; only mock measurements supported.")

# Constants
DB_PATH = 'data.db'
MIN_DURATION = 10
TABLE = 'temp_measurements'
MINUTE_S = 60
HOUR_S = 60 * 60
DAY_S = 60 * 60 * 24


def make_schema_if_needed(db_connection):
    """
    Schema generation for the monitoring tool.
    """
    make_table = (
        f"CREATE TABLE IF NOT EXISTS `{TABLE}` ("
        "`ID` INTEGER PRIMARY KEY AUTOINCREMENT,"
        "`UnixTimestamp` NUMERIC,"
        "`SampleDuration` INTEGER,"
        "`Measurement` REAL"
        ");"
    )
    make_index = (
        f"CREATE INDEX IF NOT EXISTS `search_index` ON `{TABLE}` ("
        "`SampleDuration`,"
        "`UnixTimestamp` DESC"
        ");"
    )
    db_connection.cursor().execute(make_table)
    db_connection.cursor().execute(make_index)
    db_connection.commit()


class BaseDataMonitor(ABC):
    """
    Base monitoring class to handle all data management logic.
    Implement get_reading() to have child classes provide values.
    """
    conn = None
    day_start_dt = None
    
    def __init__(self, database_conn):
        self.conn = database_conn

        # Get the last recorded day from the database and use that as the date start, if possible
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT UnixTimestamp FROM {TABLE} ORDER BY ID DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            self.day_start_dt = self.datetime_from_utc_to_local(result[0]).replace(hour=0, minute=0, second=0)
        else:
            self.day_start_dt = datetime.now().replace(hour=0, minute=0, second=0)

    @abstractmethod
    def get_reading(self) -> [float, int]:
        return None

    def datetime_from_utc_to_local(self, utc_timestamp: float) -> datetime:
        """
        Converts a UTC Unix timestamp to local time
        """
        now_timestamp = time.time()
        offset = datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(now_timestamp)
        return datetime.fromtimestamp(offset.total_seconds() + utc_timestamp)

    def insert_into_database(self, data_value: float, timestamp: int, sample_size: float):
        """
        Inserts a datapoint at the timestamp and of the given sample_size into the database.
        """
        query = f"INSERT INTO {TABLE}('UnixTimestamp', 'SampleDuration', 'Measurement') VALUES(?,?,?)"
        cursor = self.conn.cursor()
        cursor.execute(query, (timestamp, sample_size, data_value))

    def get_averaged_data(self, start_timestamp, end_timestamp):
        """
        Returns the average of the data recorded between the two timestamps that is of the minimum duration
        """
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT AVG(Measurement) FROM {TABLE} WHERE "
                       f"SampleDuration={MIN_DURATION} AND UnixTimestamp>=? AND UnixTimestamp<?",
                       (start_timestamp, end_timestamp))
        result = cursor.fetchone()
        return result[0]

    def process_datapoint(self, point: float, utc_timestamp: int):
        """
        Processes the given datapoint, performing all summarization tasks and adding it to the database.
        """
        # Generate rolling averages every new minute, hour, and day
        if utc_timestamp % MINUTE_S == 0:
            minute_average = self.get_averaged_data(utc_timestamp - MINUTE_S, utc_timestamp)
            if minute_average is not None:
                self.insert_into_database(minute_average, utc_timestamp, MINUTE_S)
        if utc_timestamp % HOUR_S == 0:
            hour_average = self.get_averaged_data(utc_timestamp - HOUR_S, utc_timestamp)
            if hour_average is not None:
                self.insert_into_database(hour_average, utc_timestamp, HOUR_S)

        # We cannot get away with using mod to find the new day, as the Unix timestamp would be in the wrong timezone
        if self.datetime_from_utc_to_local(utc_timestamp).day != self.day_start_dt.day:
            # Get the current day at midnight and the previous day, then convert to UTC for averaging in the db
            current_day = datetime.now().replace(hour=0, minute=0, second=0).replace(tzinfo=timezone.utc)
            prev_day = self.day_start_dt.replace(tzinfo=timezone.utc)
            day_average = self.get_averaged_data(prev_day.timestamp(), current_day.timestamp())
            if day_average is not None:
                self.insert_into_database(day_average, utc_timestamp, DAY_S)

        # Insert new point into database after computing averages
        self.insert_into_database(point, utc_timestamp, MIN_DURATION)
        self.conn.commit()


class MockMonitor(BaseDataMonitor):
    """
    Mock monitoring class for local testing.
    """
    def get_reading(self) -> [float, int]:
        timestamp = int(datetime.utcnow().timestamp())
        point = math.sin(timestamp * math.pi / 600)  # Gives us range of -1 to 1
        point = (point+1)/2 * 100  # Scale to 0 to 100
        return point, timestamp


class TemperatureMonitor(BaseDataMonitor):
    """
    Main temperature monitoring class.
    """
    def __init__(self, database_conn):
        super().__init__(database_conn)
        self.sensor = W1ThermSensor()
      
    def get_reading(self) -> [float, int]:
        """
        Retrieves the instantaneous measurement from the device and the timestamp it was recorded.
        """
        temp = self.sensor.get_temperature()
        temp = temp * (9.0/5.0) + 32  # Convert to F
        timestamp = int(datetime.utcnow().timestamp())
        return temp, timestamp


def __cli__():
    """
    Standalone CLI script.
    :return:
    """
    db = sqlite3.connect(DB_PATH)
    make_schema_if_needed(db)
    if "-mock" in sys.argv:
        monitor = MockMonitor(db)
    else:
        monitor = TemperatureMonitor(db)
    print("Monitor connected to database.")

    try:
        while True:
            start = time.time()
            datapoint, timestamp = monitor.get_reading()
            print(f"Processing {datapoint} at {timestamp}")
            try:
                monitor.process_datapoint(datapoint, timestamp)
            except:
                traceback.print_exc()
              
            time.sleep(MIN_DURATION - (time.time() - start))
    except KeyboardInterrupt:
        print("Captured KeyboardInterrupt; shutting down...")
    db.close()


if __name__ == "__main__":
    __cli__()
