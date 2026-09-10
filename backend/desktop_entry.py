import argparse

import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args, _unknown = parser.parse_known_args()
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port)
