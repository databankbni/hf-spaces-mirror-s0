from pypdf import PdfReader
from docx import Document
def read_uploaded_file(file):

    if file is None:
        return ""

    filename = file.name.lower()

    if filename.endswith(".txt"):

        with open(file.name, "r", encoding="utf-8") as f:
            return f.read()

    elif filename.endswith(".pdf"):

        reader = PdfReader(file.name)

        text = ""

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted

        return text

    elif filename.endswith(".docx"):

        doc = Document(file.name)

        text = "\n".join(
            para.text
            for para in doc.paragraphs
        )

        return text

    return ""