# MeadMonitor
Hobby temperature monitoring.

This project was designed for fun and is by no means perfect.

## The Idea
To record realtime temperatures into a database that can then be viewed over the *local* network.

## The Setup
A [raspberry pi](https://www.raspberrypi.org/)  zero w and [DS18B20 temperature sensor](https://www.adafruit.com/product/381) are used for raw temperature measurements. These are recorded to a local [SQLite Database](https://www.sqlite.org/index.html) on the raspberry pi.
The PI also runs an API service to expose the dataset over HTTP, which is used to generate points on a user dashboard.

Note:
- The API and data service are written in python.
- The dashboard is written with plain HTML and Javascript.

## Running Things Locally
Right now, the project is configured to run on the user's computer (with the dashboard pointing to localhost rather than the actual raspberry pi). A sample data.db file is included so no new data has to be generated. 

Instead, simply run "Monitor/monitor_api.py" and ensure the server properly starts. Then, launch "Frontend/Dashboard.html" and the sample dataset will run automatically.
## Security
This is **not** a secure setup for any kind of production monitoring, as the API service uses python's [http.server](https://docs.python.org/3/library/http.server.html) which only has basic security checks.

Furthermore, it allows for cross origin access because the dashboard is launched from a local file. This introduces another a security concern if the API is ever exposed over the larger internet.

**The Solution**? Only run this service locally, as is its intended usage.
## To Dos
- Implement full range of frontend graphs.
- Add configuration for the actual raspberry pi.
- Include directions for running on the hardware.
