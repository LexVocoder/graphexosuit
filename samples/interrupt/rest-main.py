import uvicorn
from liner import InterruptLiner
from graphexosuit.layer.backend import create_app
from langchain_classic.storage import LocalFileStore

execution_data_store = LocalFileStore(".cache/graphexosuit-samples-interrupt/execution_data_store")

app = create_app(InterruptLiner(), execution_data_store=execution_data_store)

# Serve app
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
