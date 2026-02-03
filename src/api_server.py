import uvicorn
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.index import app

if __name__ == "__main__":
    print("Starting WASDE API Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
