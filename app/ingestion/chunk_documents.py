
from pathlib import Path
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter


KNOWLEDGE_BASE_DIR = Path("data/knowledge_base")


def extract_section(text: str, start_index: int, chunk_text: str) -> str:

    # Find the last heading before the chunk starts.
    preceding_text = text[:start_index]

    previous_headings = re.findall(
        r"(?m)^#{1,6}\s+(.+)$",
        preceding_text
    )

    previous_heading = (
        previous_headings[-1].strip()
        if previous_headings
        else "Document Introduction"
    )

    # Find headings inside the current chunk.
    headings_inside_chunk = re.findall(
        r"(?m)^#{1,6}\s+(.+)$",
        chunk_text
    )

    # Prefer the first heading inside the current chunk.
    if headings_inside_chunk:
        return headings_inside_chunk[0].strip()

    return previous_heading


def load_and_chunk_documents():

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        add_start_index=True
    )

    markdown_files = sorted(KNOWLEDGE_BASE_DIR.glob("*.md"))

    if not markdown_files:
        raise FileNotFoundError(
            "No Markdown documents found in data/knowledge_base/"
        )

    all_chunks = []

    for file_path in markdown_files:

        document_text = file_path.read_text(encoding="utf-8")

        chunks = text_splitter.create_documents(
            texts=[document_text],
            metadatas=[{
                "source": file_path.name,
                "document_id": file_path.stem
            }]
        )

        for chunk_number, chunk in enumerate(chunks):

            start_index = chunk.metadata["start_index"]

            section = extract_section(
                document_text,
                start_index,
                chunk.page_content
            )

            record = {
                "chunk_id": f"{file_path.stem}-chunk-{chunk_number:03d}",
                "text": chunk.page_content,
                "source": file_path.name,
                "document_id": file_path.stem,
                "chunk_number": chunk_number,
                "start_index": start_index,
                "section": section
            }

            all_chunks.append(record)

        print(f"{file_path.name}: {len(chunks)} chunks created")

    print("\nTotal documents:", len(markdown_files))
    print("Total chunks:", len(all_chunks))

    return all_chunks


if __name__ == "__main__":

    chunks = load_and_chunk_documents()

    print("\nSAMPLE CHUNKS:")

    for chunk in chunks:

        if chunk["document_id"] == "mfa_enrollment_and_recovery":

            print("\nChunk:", chunk["chunk_number"])
            print("Section:", chunk["section"])
            print("Text:", chunk["text"][:250])












