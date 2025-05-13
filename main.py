from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
import os

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

# Use ProxyFix middleware
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
database_url = os.environ.get(
    "DATABASE_URL", 
    "sqlite:///shop.db"  # Use SQLite as fallback for local development
)

# If the URL starts with postgres:// (Heroku style), convert to postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize the app with the extension
db.init_app(app)

@app.route('/')
def home():
    return """
    <html>
    <head>
        <title>Discord Shop Bot Status</title>
        <link rel="stylesheet" href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css">
        <style>
            body { padding: 20px; }
            .status-card {
                max-width: 600px;
                margin: 50px auto;
                padding: 30px;
                border-radius: 10px;
            }
        </style>
    </head>
    <body data-bs-theme="dark">
        <div class="container">
            <div class="card status-card">
                <div class="card-body text-center">
                    <h1>Discord Shop Bot</h1>
                    <div class="my-4">
                        <span class="badge bg-success fs-5 p-2">Online & Ready</span>
                    </div>
                    <p class="lead">The Discord Shop Bot server is running.</p>
                    <p>This is the web dashboard status page for the Discord Shop Bot.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return "OK", 200

# Create tables and run the app if run directly
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)