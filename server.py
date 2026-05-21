import os
import pickle
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry, process_epub, save_to_pickle
import shutil
import tempfile

BASE_PATH = os.environ.get("BASE_PATH", "")
app = FastAPI()
templates = Jinja2Templates(directory="templates")
# Expose BASE_PATH to all templates as a Jinja2 global
templates.env.globals["base_path"] = BASE_PATH

# Where are the book folders located?
BOOKS_DIR = './chatbook'


@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None


@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        print("Scanning directory for books...")
        for item in os.listdir(BOOKS_DIR):
            print(item)
            if item.endswith("_data") and os.path.isdir(os.path.join(BOOKS_DIR,item)):
                print(item)
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append(
                        {
                            "id": item,
                            "title": book.metadata.title,
                            "author": ", ".join(book.metadata.authors),
                            "chapters": len(book.spine),
                        }
                    )

    return templates.TemplateResponse(
        "library.html", {"request": request, "books": books}
    )


@app.post("/upload")
async def upload_epub(file: UploadFile = File(...)):
    """
    Upload and process an EPUB file.
    Returns the book metadata so the UI can update immediately.
    """
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith('.epub'):
        raise HTTPException(status_code=400, detail="Only EPUB files are supported")

    # Check file size (50MB limit)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    # Create temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.epub')

    try:
        # Write uploaded content to temp file
        with os.fdopen(temp_fd, 'wb') as temp_file:
            temp_file.write(content)

        # Generate output directory name
        basename = os.path.splitext(file.filename)[0] if file.filename else "uploaded_book"
        safe_basename = "".join([c for c in basename if c.isalpha() or c.isdigit() or c in '._-()[] ']).strip()
        output_dir = os.path.join(BOOKS_DIR, f"{safe_basename}_data")

        # Check if already exists (reject duplicates)
        if os.path.exists(output_dir):
            raise HTTPException(
                status_code=409,
                detail=f"A book with the name '{safe_basename}' already exists. Please rename your file and try again."
            )

        # Process the EPUB (blocking operation)
        print(f"Processing uploaded file: {file.filename}")
        book = process_epub(temp_path, output_dir)
        save_to_pickle(book, output_dir)

        # Clear the cache so the new book appears
        load_book_cached.cache_clear()

        # Return book info for UI
        return {
            "id": f"{safe_basename}_data",
            "title": book.metadata.title,
            "author": ", ".join(book.metadata.authors),
            "chapters": len(book.spine),
            "status": "success"
        }

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        # Cleanup on error
        if 'output_dir' in locals() and os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        print(f"Error processing EPUB: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process EPUB file. Please check that the file is valid."
        )
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(book_id=book_id, chapter_index=0)


@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "book": book,
            "current_chapter": current_chapter,
            "chapter_index": chapter_index,
            "book_id": book_id,
            "prev_idx": prev_idx,
            "next_idx": next_idx,
        },
    )


@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)


if __name__ == "__main__":
    import uvicorn

    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
