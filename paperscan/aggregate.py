from pymongo import MongoClient
import os
from dotenv import load_dotenv

load.dotenv()
PDF_DIR = os.getenv("PDF_DIR")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
syllabus_collection = db[MONGO_COLLECTION]


def analyze_paper(paper_text, syllabus_topics):
    prompt = f"""You are given an academic syllabus.

Your task is to extract syllabus topics relevant to a specific exam and return a structured count of how many times each topic is covered or implied.

Rules:

Use only topics that appear explicitly in the syllabus.

Do not invent, rename, or merge topics.

If a topic is not relevant to the exam, omit it.

Count indirect mentions via subtopics or equivalent phrasing.

Output must be valid JSON only.

Do not include explanations or extra text.

Preserve exact key order and naming.

Input:

Course code: BITE301L

Exam: CAT-1

Syllabus text is provided below.

Required output schema:

{
  "course_code": "BITE301L",
  "exam": "CAT-1",
  "topics": [
    {
      "topic_name": "string",
      "count": number
    }
  ]
}


Syllabus:

{{SYLLABUS_TEXT}}


Generate the JSON now.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    return response.text

def extract_topics_from_syllabus(doc):
    syllabus = doc["extracted_syllabus"]
    topic_list = []

    for module in syllabus["modules"]:
        for topic in module["topics"]:
            topic_list.append({
                "module": module["module_title"],
                "topic": topic
            })

    return topic_list
