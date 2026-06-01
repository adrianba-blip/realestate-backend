from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/search")
def search(building: str, max_budget: int, bedrooms: int):
    return {"results": [
        {
            "source": "Example",
            "title": f"Sample listing for {building}",
            "price": f"{max_budget} PHP",
            "date": "today",
            "detail_url": "https://example.com",
            "search_url": "https://example.com/search"
        }
    ]}
