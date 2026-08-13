from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


class CustomErrorException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


@app.exception_handler(CustomErrorException)
async def custom_exception_handler(exc: CustomErrorException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
        }
    )
