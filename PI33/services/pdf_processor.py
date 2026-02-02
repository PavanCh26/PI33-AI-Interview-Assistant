import pypdf
import io

def extract_text_from_pdf(pdf_file_stream) -> str:
    """
    Extracts text from a PDF file stream.
    
    Args:
        pdf_file_stream: A file-like object containing the PDF data.
        
    Returns:
        str: The extracted text from the PDF.
    """
    try:
        reader = pypdf.PdfReader(pdf_file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""
