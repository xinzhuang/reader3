# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reader3 is a lightweight, self-hosted EPUB reader designed for reading books with LLMs. It processes EPUB files into structured data and serves them via a web interface, one chapter at a time. This architecture makes it easy to copy chapter contents to LLMs for collaborative reading.

## Development Commands

### Processing EPUB Files
```bash
uv run reader3.py <file.epub>
```
Creates a `{filename}_data/` directory containing:
- `book.pkl` - Serialized Book object with all content
- `images/` - Extracted images from the EPUB

### Running the Web Server
```bash
uv run server.py
```
Starts the FastAPI server at http://127.0.0.1:8123

### Environment Setup
The project uses [uv](https://docs.astral.sh/uv/) as the package manager. All dependencies are defined in [pyproject.toml](pyproject.toml) and locked in [uv.lock](uv.lock).

## Architecture

### Core Components

**[reader3.py](reader3.py)** - EPUB Processing Pipeline
- Parses EPUB files using `ebooklib` and `BeautifulSoup`
- Converts EPUB structure into clean Python dataclasses
- Extracts and sanitizes images, rewriting their paths in HTML
- Builds hierarchical TOC (Table of Contents) with fallback to spine-based generation
- Outputs serialized Book objects via pickle for fast loading

**[server.py](server.py)** - FastAPI Web Server
- Serves library view listing all processed books
- Provides chapter-by-chapter reading interface
- Implements LRU caching (`@lru_cache`) for book loading to avoid repeated disk I/O
- Routes:
  - `/` - Library view (scans `BOOKS_DIR` for `*_data/` folders with `book.pkl`)
  - `/read/{book_id}/{chapter_index}` - Chapter reader
  - `/read/{book_id}/images/{image_name}` - Image serving

**[templates/](templates/)** - Jinja2 HTML Templates
- `library.html` - Grid view of all processed books
- `reader.html` - Two-panel reading interface with:
  - Left sidebar: Recursive TOC navigation
  - Main content: Current chapter with Previous/Next navigation
  - JavaScript bridge: Maps TOC filenames to spine indices for navigation

### Data Flow

```
EPUB file → reader3.py → {name}_data/
                          ├── book.pkl (Book object)
                          └── images/ (extracted images)

Server loads book.pkl (cached) → Renders template → Browser
```

### Key Data Structures ([reader3.py:17-67](reader3.py#L17-L67))

- **Book**: Master object containing metadata, spine (linear chapters), TOC (hierarchical), and image mappings
- **ChapterContent**: Represents a physical file in the EPUB spine with cleaned HTML and plain text
- **TOCEntry**: Logical navigation entries with support for nested children
- **BookMetadata**: EPUB metadata (title, authors, description, etc.)

### Critical Implementation Details

**Image Handling**:
- Images are extracted from EPUB and saved to `{book_data}/images/`
- HTML `src` attributes are rewritten to point to `/read/{book_id}/images/{filename}`
- Both full paths and basenames are mapped for robustness against messy EPUB internal paths

**TOC vs Spine**:
- **Spine**: Linear reading order (physical files in EPUB)
- **TOC**: Hierarchical navigation structure (logical chapters)
- Multiple TOC entries can point to the same spine file (different anchors)
- TOC can be empty, triggering fallback generation from spine

**Navigation Challenge**:
- TOC entries reference filenames/anchors, not linear indices
- Server routes use linear spine indices
- JavaScript in `reader.html:124-151` builds a mapping from filenames to spine indices

**Configuration**:
- `BOOKS_DIR` in [server.py:17](server.py#L17) defines where processed books are stored
- Currently hardcoded to `/Volumes/My Passport/Ebook/金字塔原理`
- Modify this path to change the library location

## Dependencies

- **ebooklib**: EPUB file parsing
- **beautifulsoup4**: HTML cleaning and manipulation
- **fastapi**: Web framework
- **uvicorn**: ASGI server
- **jinja2**: HTML templating

## File Organization

- `*_data/` directories are generated and ignored by git
- `*.epub` files should be placed in project root for processing
- The `.venv` directory contains the Python virtual environment
