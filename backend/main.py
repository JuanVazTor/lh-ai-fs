from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from pipeline import run_pipeline

app = FastAPI(title="BS Detector")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCUMENTS_DIR = Path(__file__).parent / "documents"


def load_documents() -> dict[str, str]:
    """Load all documents from the documents directory."""
    documents = {}
    for file_path in DOCUMENTS_DIR.glob("*.txt"):
        documents[file_path.stem] = file_path.read_text()
    return documents


@app.post("/analyze")
async def analyze():
    """Run the multi-agent verification pipeline over the case file."""
    documents = load_documents()
    state = run_pipeline(documents)
    return {
        "report": {
            "citations": [c.model_dump() for c in state.citations],
            "flags": [f.model_dump() for f in state.flags],
            "judicial_memo": state.judicial_memo,
            "errors": state.errors,
        }
    }
