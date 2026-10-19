"""Start the POC: python run.py, then open http://localhost:8000"""
from poc import config
from poc.server import app

if __name__ == "__main__":
    status = f"OpenAI ready ({config.OPENAI_MODEL})" if config.openai_enabled() else \
        "OPENAI_API_KEY missing: add it to .env and restart"
    print(f"\n  Cars24 pre-inspection POC\n  {status}\n  Open http://localhost:{config.PORT}\n")
    app.run(host="127.0.0.1", port=config.PORT, debug=False, threaded=True)
