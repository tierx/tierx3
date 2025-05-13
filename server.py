from flask import Flask
from threading import Thread
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('server')

app = Flask('')

@app.route('/')
def home():
    return "Discord shop bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run():
    # Use 0.0.0.0 to bind to all interfaces
    # Port 8000 as specified in requirements
    app.run(host='0.0.0.0', port=8000)

def keep_alive():
    """Start the Flask server in a separate thread to keep the bot alive"""
    logger.info("Starting web server thread")
    t = Thread(target=run)
    t.daemon = True  # Set as daemon so it exits when the main thread exits
    t.start()
    logger.info("Web server thread started")
