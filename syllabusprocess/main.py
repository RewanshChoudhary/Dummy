import google.generativeai as genai

import os
from pdf2image import convert_from_path
import pytesseract
from pymongo import MongoClient
import json

from dotenv import load_dotenv
load_dotenv()
PDF_DIR = os.getenv("PDF_DIR")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION_SYLLABUS")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_PROMPT= """

Extract a structured syllabus from the provided document.
Follow these rules:

1. Preserve sequencing: course info → objectives → outcomes → modules → textbooks → reference books → evaluation.
2. Do not hallucinate. Use only information explicitly in the document.
3. Maintain exact module order, titles, and hours.
4. Missing sections must be empty arrays or empty strings.
5. Output strictly valid JSON. No explanations, no comments, no extra text.
6. (High Priority) Should properly scan and give proper syllabus module wise
Output JSON structure:
{ 
  "course_code": "" ...course_code_example=BCHY101L and it should be included ALWAYS..., 
  "course_title": "",
  "pre_requisite": "",
  "course_objectives": [],
  "course_outcomes": [],
  "modules": [],
  
  "reference_books": [],
  
  
  
}

Module rules: module_number, module_title, hours, topics[].
Textbook/reference entries must keep numbering and full text.

Return only the JSON object.
"""

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
coll = db[MONGO_COLLECTION]
print("Resolved PDF_DIR:", PDF_DIR)
print("Directory exists:", os.path.exists(PDF_DIR))
print("Files inside:", os.listdir(PDF_DIR))


def extract_ocr_from_pdf(pdf_path):
    pages = convert_from_path(pdf_path, dpi=300)
    text_chunks = []
    for page in pages:
        text_chunks.append(
            pytesseract.image_to_string(page, config="--psm 6")
        )
    return "\n".join(text_chunks)


def extract_syllabus_json(ocr_text):
    prompt = GEMINI_PROMPT + "\n\nOCR TEXT STARTS BELOW:\n\n" + ocr_text

   
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )


   
    raw = response.text
    if raw is None or raw.strip() == "":
        raise ValueError("Gemini returnedempty output check OCR or prompt.")

    return json.loads(raw)

def store_in_mongo(course_code, syllabus_json):
    doc = {
        "course_code": course_code,
        
        "extracted_syllabus": syllabus_json
        
    }
    # Inserts if not present and replaces if present
    coll.replace_one(
        {"course_code": course_code},  
        doc,                           
        upsert=True                    
    )




def process_folder():
    for file in os.listdir(PDF_DIR):
        if not file.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(PDF_DIR, file)
        print("Processing:", pdf_path)

        ocr_text = extract_ocr_from_pdf(pdf_path)
        print("OCR length:", len(ocr_text))

        
        syllabus_json = extract_syllabus_json(ocr_text)

        filename_no_ext = os.path.splitext(file)[0]
        course_code = filename_no_ext.split("_")[0]

        store_in_mongo(course_code,  syllabus_json)

        print("Done:", course_code)


if __name__ == "__main__":
    process_folder()

    
