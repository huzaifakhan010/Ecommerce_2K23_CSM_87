from fastapi import FastAPI

from app.errors import register_exception_handlers
from app.routers import admin, auth

app = FastAPI(
    title="Custom Print-on-Demand Studio API",
    version="0.2.0",
    description="Sprint 2: catalog data foundation (categories, products, variants, SKUs).",
)
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
