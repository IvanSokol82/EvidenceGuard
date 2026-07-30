from dataclasses import dataclass


@dataclass
class ChunkPayload:
    chunk_index: int
    content: str
    page_reference: str | None
    section_reference: str | None


def chunk_text(
    text: str,
    max_chunk_size: int = 600,
    overlap: int = 100,
    page_reference: str | None = None,
    section_reference: str | None = None,
    start_chunk_index: int = 0,
) -> list[ChunkPayload]:
    """
    Splits text into chunks of max_chunk_size characters with overlap,
    preserving paragraph and sentence boundaries where possible.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        return []

    if len(cleaned_text) <= max_chunk_size:
        return [
            ChunkPayload(
                chunk_index=start_chunk_index,
                content=cleaned_text,
                page_reference=page_reference,
                section_reference=section_reference,
            )
        ]

    chunks: list[ChunkPayload] = []
    current_idx = start_chunk_index
    paragraphs = cleaned_text.split("\n\n")

    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 <= max_chunk_size:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                chunks.append(
                    ChunkPayload(
                        chunk_index=current_idx,
                        content=current_chunk,
                        page_reference=page_reference,
                        section_reference=section_reference,
                    )
                )
                current_idx += 1
                # Preserve overlap from tail of current_chunk
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
            else:
                # Paragraph is larger than max_chunk_size, force split by characters
                for i in range(0, len(para), max_chunk_size - overlap):
                    sub_chunk = para[i : i + max_chunk_size]
                    chunks.append(
                        ChunkPayload(
                            chunk_index=current_idx,
                            content=sub_chunk,
                            page_reference=page_reference,
                            section_reference=section_reference,
                        )
                    )
                    current_idx += 1
                current_chunk = ""

    if current_chunk:
        chunks.append(
            ChunkPayload(
                chunk_index=current_idx,
                content=current_chunk,
                page_reference=page_reference,
                section_reference=section_reference,
            )
        )

    return chunks
