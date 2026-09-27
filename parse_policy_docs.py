import os
import json
import pdfplumber

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNKS_FILE = os.path.join(BASE_DIR, 'chunks.json')

def is_heading(line: str) -> bool:
    """
    Heuristically determine if a line is a section heading.
    """
    line = line.strip()
    if not line:
        return False
    
    # Check length
    if len(line) >= 80:
        return False
        
    # Check if it starts with a capital letter
    if not line[0].isupper():
        return False

    # Common explicit headings
    common_headings = [
        'Eligibility Criteria', 'Plan Details', 'Wait Periods', 'Key Coverages', 
        'Introduction', 'Additional Coverages', 'Optional Benefits', 'About Us', 
        'Preventive Health Check-up', 'Home Healthcare', 'Exclusions'
    ]
    if any(line.lower().startswith(h.lower()) for h in common_headings):
        return True

    # All caps
    if line.isupper() and len(line) > 3:
        return True

    # Title case (mostly title cased)
    words = line.split()
    if not words:
        return False
    title_cased = [w for w in words if w.istitle() or w.isupper()]
    if len(title_cased) / len(words) > 0.5:
        return True

    # Ends with colon
    if line.endswith(':'):
        return True

    return False

def parse_pdf(pdf_path: str) -> list[dict]:
    """
    Parse a single PDF file into a list of chunks.
    """
    doc_name = os.path.splitext(os.path.basename(pdf_path))[0]
    doc_name_slug = doc_name.lower().replace(' ', '_')
    chunks = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            current_chunk_text = []
            current_section_title = None
            current_page_number = None
            section_idx = 0

            for page_idx, page in enumerate(pdf.pages):
                page_number = page_idx + 1
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split('\n')
                headings_found_on_page = False
                
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                        
                    if is_heading(line_str):
                        headings_found_on_page = True
                        
                        # Save previous chunk
                        if current_chunk_text:
                            chunks.append({
                                'chunk_id': f"{doc_name_slug}_{section_idx}",
                                'doc_name': doc_name,
                                'section_title': current_section_title or f"Page {current_page_number}",
                                'text': '\n'.join(current_chunk_text),
                                'page_number': current_page_number
                            })
                            section_idx += 1
                        
                        # Start new chunk
                        current_section_title = line_str
                        current_page_number = page_number
                        current_chunk_text = [line_str]
                    else:
                        if current_chunk_text:
                            current_chunk_text.append(line_str)
                        else:
                            # Handling text before first heading
                            current_section_title = f"Page {page_number}"
                            current_page_number = page_number
                            current_chunk_text = [line_str]

                # If no headings found on page, treat entire page as one chunk (or append if none found overall)
                if not headings_found_on_page:
                    if not current_chunk_text:
                        current_section_title = f"Page {page_number}"
                        current_page_number = page_number
                        current_chunk_text = lines
            
            # Add the last chunk
            if current_chunk_text:
                chunks.append({
                    'chunk_id': f"{doc_name_slug}_{section_idx}",
                    'doc_name': doc_name,
                    'section_title': current_section_title or f"Page {current_page_number}",
                    'text': '\n'.join(current_chunk_text),
                    'page_number': current_page_number
                })
    except Exception as e:
        print(f"Error parsing {pdf_path}: {e}")
        
    return chunks

def parse_all_docs(policy_dir: str = 'policies') -> list[dict]:
    """
    Extracts text from PDF files in the given directory and saves them to chunks.json.
    Only re-parses if any PDF's mtime is newer than chunks.json.
    """
    if not os.path.isabs(policy_dir):
        policy_dir = os.path.join(BASE_DIR, policy_dir)
        
    pdfs = []
    if os.path.exists(policy_dir):
        pdfs = [os.path.join(policy_dir, f) for f in os.listdir(policy_dir) if f.lower().endswith('.pdf')]
    
    if not pdfs:
        print(f"No PDFs found in {policy_dir}")
        return []

    needs_parse = True
    if os.path.exists(CHUNKS_FILE):
        try:
            chunks_mtime = os.path.getmtime(CHUNKS_FILE)
            pdf_mtimes = [os.path.getmtime(pdf) for pdf in pdfs]
            if max(pdf_mtimes) < chunks_mtime:
                needs_parse = False
        except Exception:
            pass
            
    if not needs_parse:
        print("Using cached chunks.json")
        try:
            with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading chunks.json: {e}")
            needs_parse = True
            
    print("Parsing PDFs...")
    all_chunks = []
    for pdf in pdfs:
        print(f"Parsing {pdf}")
        chunks = parse_pdf(pdf)
        all_chunks.extend(chunks)
        
    try:
        with open(CHUNKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(all_chunks)} chunks to {CHUNKS_FILE}")
    except Exception as e:
        print(f"Error saving chunks.json: {e}")
        
    return all_chunks

def load_chunks(doc_names: list[str] | None = None) -> list[dict]:
    """
    Loads chunks from chunks.json, optionally filtering by doc_name.
    """
    if not os.path.exists(CHUNKS_FILE):
        print(f"{CHUNKS_FILE} not found. Call parse_all_docs() first.")
        return []
        
    try:
        with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
            
        if doc_names:
            chunks = [c for c in chunks if c.get('doc_name') in doc_names]
            
        return chunks
    except Exception as e:
        print(f"Error reading {CHUNKS_FILE}: {e}")
        return []

def get_available_docs(policy_dir: str = 'policies') -> list[dict]:
    """
    Returns list of all available policy documents with chunk counts.
    """
    chunks = load_chunks()
    doc_map = {}
    for c in chunks:
        doc = c.get('doc_name')
        if doc:
            doc_map[doc] = doc_map.get(doc, 0) + 1
    
    # Also check policy directory for any PDFs
    if not os.path.isabs(policy_dir):
        policy_dir = os.path.join(BASE_DIR, policy_dir)
    
    results = []
    if os.path.exists(policy_dir):
        for f in sorted(os.listdir(policy_dir)):
            if f.lower().endswith('.pdf'):
                doc_name = os.path.splitext(f)[0]
                results.append({
                    "doc_name": doc_name,
                    "filename": f,
                    "chunk_count": doc_map.get(doc_name, 0)
                })
    return results

def add_and_parse_doc(file_bytes: bytes, filename: str, policy_dir: str = 'policies') -> dict:
    """
    Saves an uploaded policy PDF, parses its sections, and updates chunks.json.
    """
    if not os.path.isabs(policy_dir):
        policy_dir = os.path.join(BASE_DIR, policy_dir)
    os.makedirs(policy_dir, exist_ok=True)
    
    # Clean filename
    clean_name = filename.replace(" ", "_")
    target_path = os.path.join(policy_dir, clean_name)
    with open(target_path, "wb") as f:
        f.write(file_bytes)
        
    doc_name = os.path.splitext(clean_name)[0]
    new_chunks = parse_pdf(target_path)
    
    # Merge with existing chunks
    existing_chunks = []
    if os.path.exists(CHUNKS_FILE):
        try:
            with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
                existing_chunks = json.load(f)
        except Exception:
            existing_chunks = []
            
    # Filter out any prior chunks for this doc_name
    filtered_chunks = [c for c in existing_chunks if c.get('doc_name') != doc_name]
    filtered_chunks.extend(new_chunks)
    
    with open(CHUNKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(filtered_chunks, f, indent=2, ensure_ascii=False)
        
    return {
        "doc_name": doc_name,
        "filename": clean_name,
        "new_chunk_count": len(new_chunks),
        "total_chunk_count": len(filtered_chunks)
    }

if __name__ == "__main__":
    chunks = parse_all_docs()
    print(f"Total chunks: {len(chunks)}")
    if chunks:
        print(f"Sample chunk: {chunks[0]['doc_name']} - {chunks[0]['section_title']}")
