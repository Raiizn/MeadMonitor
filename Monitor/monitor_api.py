import json
import sqlite3
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from sqlite3 import Connection
from datetime import datetime

DB_PATH = "data.db"
HOST = ""
PORT = 4098
START_TIME = datetime.now()
CODE_OK = 200
MIN_SAMPLE_SIZE = 10

class BasicServerHandler(BaseHTTPRequestHandler):
    """
     Basic http server class that supports registering handlers for GET locations
    """
    handlers = {}

    @staticmethod
    def register_handler(path, handler: "Callable[BasicServerHandler, dict]"):
        """
        Registers the given function to be fired when the specified path is accessed by the user.
        """
        BasicServerHandler.handlers[path] = handler

    def write_headers(self, status_code):
        """
        Writes all necessary HTTP headers for an API response.
        """
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers",
                         "Accept, X-Access-Token, X-Application-Name, X-Request-Sent-Time")
        # Only allow GET requests.. Normally this is GET, POST, and OPTIONS
        self.send_header("Access-Control-Allow-Methods", "GET")
        # Don't care about the origin for this API
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def write(self, msg):
        self.wfile.write(bytes(msg, "utf-8"))
        self.wfile.flush()

    def write_response(self, msg, code=200):
        self.write_headers(code)
        self.write(msg)

    def write_error(self, msg, code=500):
        self.write_headers(code)
        self.write(json.dumps({
            "error": msg,
        }))

    def do_GET(self):
        path = self.path.split('?')
        location = path[0]

        # Strip leading /
        while len(location) > 0 and location[0] == '/':
            location = location[1:]

        # Do nothing on the root
        if len(location) == 0:
            self.write_headers(200)
            self.write("")
            return

        params = {}
        if len(path) > 1:
            param_str = path[1]
        else:
            param_str = ''

        # Parameterize url
        if param_str != '':
            pieces = param_str.split('&')
            for piece in pieces:
                index = piece.find('=')
                if index > -1:
                    key = piece[:index].strip()
                    val = piece[index + 1:].strip()
                else:
                    key = piece
                    val = None
                params[key] = val

        # Trigger registered handlers
        if location in BasicServerHandler.handlers:
            BasicServerHandler.handlers[location](self, params)
        else:
            self.write_error('Unsupported Request: ' + location, 404)


def fetch_data(handler: BasicServerHandler, params: dict, db_conn: Connection, sample_size: int,):
    """
    Main API function.
    This accesses the local database to find all samples of the given sample size that are within the start and end
    dates passed into the parameters.
    """
    start_utc, end_utc = None, None

    # Validate start parameter
    if "start" not in params:
        handler.write_error("'start' parameter missing from request.")
        return
    try:
        start_utc = int(params["start"])
    except ValueError:
        handler.write_error("'start' parameter could not be converted to an integer.")
        return

    # ... and end parameter
    if "end" in params:
        try:
            end_utc = int(params["end"])
        except ValueError:
            handler.write_error("'end' parameter could not be converted to an integer.")

    # Retrieve data
    cursor = db_conn.cursor()
    query = ("SELECT UnixTimestamp,Measurement FROM temp_measurements "
             "WHERE SampleDuration=? AND UnixTimestamp>=?")
    if end_utc:
        query += " AND UnixTimestamp<? ORDER BY ID ASC"
        cursor.execute(query, [sample_size, start_utc, end_utc])
    else:
        query+= " ORDER BY ID ASC"
        cursor.execute(query, [sample_size, start_utc])
    results = cursor.fetchall()

    handler.write_response(json.dumps(results))


def fetch_latest(handler: BasicServerHandler, _, db_conn: Connection):
    """
    API function that retrieves the latest sample of size 1
    """
    cursor = db_conn.cursor()
    cursor.execute(f"SELECT UnixTimestamp,Measurement FROM temp_measurements "
                   f"WHERE SampleDuration={MIN_SAMPLE_SIZE} ORDER BY ID DESC LIMIT 1")
    r = cursor.fetchone()
    if not r:
        handler.write_error("No data")
        return

    handler.write_response(json.dumps(r))


def __cli__():
    """
    Standalone CLI script.
    """
    db = sqlite3.connect(DB_PATH)
    web_server = HTTPServer((HOST, PORT), BasicServerHandler)

    # Register all API paths
    BasicServerHandler.register_handler("latest", lambda a, b: fetch_latest(a, b, db))
    BasicServerHandler.register_handler("all", lambda a, b: fetch_data(a, b, db, MIN_SAMPLE_SIZE))
    BasicServerHandler.register_handler("minutes", lambda a, b: fetch_data(a, b, db, 60))
    BasicServerHandler.register_handler("hours", lambda a, b: fetch_data(a, b, db, 60*60))
    BasicServerHandler.register_handler("days", lambda a, b: fetch_data(a, b, db, 60*60*24))

    print("Server started http://%s:%s" % (HOST, PORT))

    try:
        web_server.serve_forever()
    except (KeyboardInterrupt, OSError):
        print("Closing...")
    web_server.server_close()
    db.close()

    print("Server done.")


if __name__ == "__main__":
    __cli__()
