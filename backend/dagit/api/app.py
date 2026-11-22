from fastapi import FastAPI

from dagit.api.routes import router


app = FastAPI(title="DataGit API")
app.include_router(router)
