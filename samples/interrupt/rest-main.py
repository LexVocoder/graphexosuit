import uvicorn
from liner import build_graph, get_checkpointer_cm
from fastapi.staticfiles import StaticFiles
from graphexosuit.layer.backend import create_app
from langchain_classic.storage import LocalFileStore

execution_data_store = LocalFileStore(".cache/graphexosuit-samples-interrupt/execution_data_store")

app = create_app(
    graph=build_graph(),
    checkpointer_cm=get_checkpointer_cm(),
    execution_data_store=execution_data_store,
)

app.mount("/", StaticFiles(directory="/home/micro/repos/trusted/graphexosuit-webfrontend/dist", html=True), name="frontend")

# Serve app
if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
