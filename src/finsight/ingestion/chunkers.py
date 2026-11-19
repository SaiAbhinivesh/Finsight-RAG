"""Split page Documents into smaller chunks."""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_documents(
    documents: list[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,        # max characters per chunk
        chunk_overlap=chunk_overlap,  # characters repeated between neighbours
        add_start_index=True,         # records where in the page each chunk starts
    )
    return splitter.split_documents(documents)