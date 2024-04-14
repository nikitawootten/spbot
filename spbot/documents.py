"""
Handles creating and loading the vector DB
"""

import os
import logging

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings.ollama import OllamaEmbeddings
from langchain_text_splitters import CharacterTextSplitter

from spbot.common import CACHE_DIR
from spbot.csrc_api import PublicationResolver


logger = logging.getLogger(__name__)


CHROMA_DB_PATH = os.path.join(CACHE_DIR, "chroma")
CHROMA_COLLECTION_NAME = "documents"


def get_retreiver():
    chroma = Chroma(
        embedding_function=OllamaEmbeddings(),
        collection_name=CHROMA_COLLECTION_NAME,
        persist_directory=CHROMA_DB_PATH,
    )
    documents = load_documents()
    chroma.add_documents(documents)
    return chroma.as_retriever()


def load_documents():
    documents = []
    resolver = PublicationResolver()

    logger.info("Loading document list")
    listing = resolver.list_documents().items()
    logger.info(f"Found {len(listing)} documents, retreiving texts")
    for name, details in listing:
        cached_links = set()
        for link in details["publication_links"]:
            cached_link = resolver.get_cached_publication_file(link)
            if not cached_link:
                logger.warning(f"Skipping bad link {link}")
                continue
            cached_links.add(resolver.get_cached_publication_file(link))

        for cached_link in cached_links:
            if cached_link.endswith(".pdf"):
                loader = PyPDFLoader(cached_link)
                documents.extend(loader.load())

    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=10)
    return text_splitter.split_documents(documents)
