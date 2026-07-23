from fastapi import FastAPI

app = FastAPI(
    title="ArXiv Research Assistant",
    version="2.0.0",
    description="Uçtan uca AI araştırma asistanı — V2.0: FastAPI katmanı"
)


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """
    Sistem canlılık kontrolü.
    Şu an sadece process'in ayakta olduğunu doğrular.
    Adım 4'te buraya DB bağlantı kontrolü eklenecek (readiness check farkı).
    """
    return {"status": "ok"}