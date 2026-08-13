import time
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware


async def log(request: Request, call_next):
    """
    Add API process time in response headers and log calls
    """
    start_time = time.time()
    response: Response = await call_next(request)
    process_time = str(round(time.time() - start_time, 3))
    response.headers["X-Process-Time"] = process_time

    return response
