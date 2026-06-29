from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("backend.app.api:app", host="127.0.0.1", port=9127, reload=True)

