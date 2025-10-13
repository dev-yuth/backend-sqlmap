# manage.py
import asyncio
import sys
from app import create_app
from app.extensions import db
from flask_migrate import Migrate

# --- START: Fix for asyncio on Windows ---
# This checks if the operating system is Windows and sets a different
# event loop policy that is more compatible and avoids ConnectionResetError.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# --- END: Fix for asyncio on Windows ---

app = create_app()
migrate = Migrate(app, db)
# print("manage.py imported - creating app and migrate")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
