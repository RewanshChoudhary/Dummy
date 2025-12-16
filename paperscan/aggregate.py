from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv()
QUESTION_DIR = os.getenv("QUESTION_DIR")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION_SYLLABUS")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
prompt=

stats_col = db["topic_stats"]
from pdf2image import convert_from_path
import pytesseract

def ocr_pdf(pdf_path: str):
    pages = convert_from_path(pdf_path, dpi=300)

    ocr_pages = []
    for i, page in enumerate(pages):
        text = pytesseract.image_to_string(page)
        ocr_pages.append({
            "page": i + 1,
            "text": text
        })

    return ocr_pages


def call_llm(prompt: str) -> dict:
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    

    
    return json.loads(content)