import pytest
from backend.rag.embeddings import get_embedding_model
from backend.rag.vectorstore import get_vectorstore
from backend.rag.loader import load_and_split
from backend.config import settings
from unittest.mock import patch, MagicMock


def test_get_embedding_model_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedding_model("unknown")


def test_load_and_split_uses_text_loader_for_txt():
    with patch("backend.rag.loader.TextLoader") as mock_loader:
        mock_doc = MagicMock()
        mock_doc.page_content = "test content"
        mock_doc.metadata = {}
        mock_loader.return_value.load.return_value = [mock_doc]
        load_and_split("test.txt")
        mock_loader.assert_called_once_with("test.txt", encoding="utf-8")


def test_load_and_split_uses_pdf_loader_for_pdf():
    with patch("backend.rag.loader.PyPDFLoader") as mock_loader:
        mock_doc = MagicMock()
        mock_doc.page_content = "pdf content"
        mock_doc.metadata = {}
        mock_loader.return_value.load.return_value = [mock_doc]
        load_and_split("test.pdf")
        mock_loader.assert_called_once_with("test.pdf")


def test_get_vectorstore_returns_chroma():
    with patch("langchain_chroma.Chroma") as mock_chroma, patch(
        "backend.rag.vectorstore.get_embedding_model"
    ) as mock_embed:
        mock_chroma.return_value = MagicMock()
        mock_embed.return_value = MagicMock()
        vs = get_vectorstore("test_collection")
        mock_chroma.assert_called_once()
        call_kwargs = mock_chroma.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["persist_directory"] == settings.chroma_dir
