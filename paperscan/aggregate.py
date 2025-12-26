import json
import os
import re
import time

import google.generativeai as genai
import pytesseract
from dotenv import load_dotenv
from pdf2image import convert_from_path
from pymongo import MongoClient

load_dotenv()
QUESTION_DIR = os.getenv("QUESTION_DIR")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION_SYLLABUS = os.getenv("MONGO_COLLECTION_SYLLABUS")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client[MONGO_DB]
    stats_col = db["topic_stats"]
except Exception as e:
    db = None
    stats_col = None

def ocr_pdf_as_string(pdf_path: str) -> str:
    pages = convert_from_path(pdf_path, dpi=300)

    text = []
    for page in pages:
        text.append(pytesseract.image_to_string(page))

    return "\n\n".join(text)

def generate_prompt(course_code: str, questions_text: str) -> str:
    if db is None:
        raise ConnectionError("MongoDB connection not available. Cannot fetch syllabus.")
    
    syllabus = db[MONGO_COLLECTION_SYLLABUS].find_one(
        {"course_code": course_code},
        {"_id": 0}
    )
    
    if syllabus is None:
        raise ValueError(f"NO SYLLABUS FOUND for course_code: {course_code}")
    
    syllabus_json = json.dumps(syllabus, indent=2)
    
    PROMPT_TEMPLATE = """
You are given:
1. A course syllabus in JSON format (modules and topics)
2. A complete question paper

Task:
Identify which syllabus topic(s) appear in the question paper and count how many times each topic appears (count each question/mention of the topic).

Rules:
- Choose ONLY from the topics explicitly listed in the syllabus JSON
- Do NOT invent topics
- Do NOT output module numbers
- Count ALL occurrences of each topic (if a topic appears in multiple questions, count each occurrence)
- If no topic matches, return an empty list
- Return valid JSON only

Syllabus:
{syllabus}

Question Paper :
{questions}

Output format:
{{
  "matched_topics": [
    {{"topic": "topic_name", "count": number_of_occurrences}}
  ]
}}
"""
    
    return PROMPT_TEMPLATE.format(
        syllabus=syllabus_json,
        questions=questions_text
    )


def call_llm(course_code: str, questions_text: str, max_retries: int = 5) -> dict:
    prompt = generate_prompt(course_code, questions_text)
    
    for attempt in range(max_retries):
        try:
            combined_response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            topic_json = combined_response.text
            
            if topic_json is None or topic_json.strip() == "":
                raise ValueError("Gemini returned an empty string")
            
            return json.loads(topic_json)
        
        except Exception as e:
            error_str = str(e)
            
            if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
                wait_time = (2 ** attempt) * 10
                if "retry in" in error_str.lower():
                    try:
                        retry_match = re.search(r"retry in ([\d.]+)s", error_str, re.IGNORECASE)
                        if retry_match:
                            wait_time = float(retry_match.group(1)) + 5
                    except:
                        pass
                
                if attempt < max_retries - 1:
                    print(f"Rate limit hit. Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Rate limit exceeded after {max_retries} retries: {e}")
            else:
                raise


def split_topics(topics_string: str) -> list:
    parts = re.split(r"[-–—]", topics_string)
    return [p.strip() for p in parts if p.strip()]


def find_topic_module(course_code: str, topic: str) -> str:
    if db is None:
        return None
    
    syllabus = db[MONGO_COLLECTION_SYLLABUS].find_one({"course_code": course_code})
    
    if syllabus is None:
        return None
    
    modules = syllabus["extracted_syllabus"]["modules"]
    topic_normalized = topic.lower().strip()
    
    for module in modules:
        module_number = module["module_number"]
        topics_list = module.get("topics", [])
        
        for topic_string in topics_list:
            individual_topics = split_topics(topic_string)
            
            for individual_topic in individual_topics:
                individual_topic_normalized = individual_topic.lower().strip()
                
                if (topic_normalized == individual_topic_normalized or 
                    topic_normalized in individual_topic_normalized or
                    individual_topic_normalized in topic_normalized):
                    return module_number
    
    return None


def update_topic_stats(course_code: str, exam_type: str, matched_topics: list):
    if stats_col is None:
        return
    
    for topic_item in matched_topics:
        topic = topic_item.get("topic", "")
        topic_count = topic_item.get("count", 1)
        
        if not topic:
            continue
        
        module_number = find_topic_module(course_code, topic)
        
        if module_number is None:
            continue
        
        query = {
            "course_code": course_code,
            "exam_type": exam_type,
            "module_number": module_number,
            "topic": topic
        }
        
        stats_col.update_one(
            query,
            {"$inc": {"count": topic_count}},
            upsert=True
        )
        print(f"Updated: {course_code} - {exam_type} - Module {module_number} - {topic} (count: +{topic_count})")


def extract_course_code_and_exam_type(filename: str) -> tuple:
    filename_no_ext = os.path.splitext(filename)[0]
    parts = filename_no_ext.split("-")
    
    if len(parts) < 2:
        raise ValueError(f"Cannot parse filename: {filename}")
    
    course_code = parts[0]
    exam_type = parts[1]
    
    return course_code, exam_type


def process_paper(pdf_path: str, course_code: str = None, exam_type: str = None):
    if course_code is None or exam_type is None:
        filename = os.path.basename(pdf_path)
        extracted_code, extracted_type = extract_course_code_and_exam_type(filename)
        course_code = course_code or extracted_code
        exam_type = exam_type or extracted_type
    
    print(f"Processing: {pdf_path}")
    print(f"Course Code: {course_code}, Exam Type: {exam_type}")
    
    questions_text = ocr_pdf_as_string(pdf_path)
    result = call_llm(course_code, questions_text)
    matched_topics = result.get("matched_topics", [])
    
    if matched_topics:
        total_occurrences = sum(item.get("count", 1) for item in matched_topics)
        print(f"Matched {len(matched_topics)} unique topics with {total_occurrences} total occurrences")
        for item in matched_topics:
            print(f"  - {item.get('topic', '')}: {item.get('count', 0)} times")
    
    update_topic_stats(course_code, exam_type, matched_topics)
    print(f"Completed: {course_code} - {exam_type}")


def process_all_question_papers(question_dir: str = None):
    if question_dir is None:
        question_dir = QUESTION_DIR
    
    if not os.path.exists(question_dir):
        raise ValueError(f"Question directory does not exist: {question_dir}")
    
    course_papers = {}
    
    for filename in os.listdir(question_dir):
        if not filename.lower().endswith(".pdf"):
            continue
        
        try:
            course_code, _ = extract_course_code_and_exam_type(filename)
            
            if course_code not in course_papers:
                course_papers[course_code] = []
            
            course_papers[course_code].append(filename)
        except Exception as e:
            print(f"Warning: Could not extract course code from {filename}: {e}")
            continue
    
    total_papers = sum(len(papers) for papers in course_papers.values())
    total_processed = 0
    total_errors = 0
    
    print(f"\nProcessing all question papers")
    print(f"Found {len(course_papers)} course(s) with {total_papers} total papers\n")
    
    for course_code, papers in sorted(course_papers.items()):
        print(f"\n{'='*60}")
        print(f"Course: {course_code} ({len(papers)} papers)")
        print(f"{'='*60}")
        
        for idx, filename in enumerate(sorted(papers), 1):
            pdf_path = os.path.join(question_dir, filename)
            
            try:
                print(f"\nPaper {idx}/{len(papers)}: {filename}")
                process_paper(pdf_path, course_code=course_code)
                total_processed += 1
            except KeyboardInterrupt:
                print("\n\nProcessing interrupted by user")
                raise
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                total_errors += 1
                continue
    
    print(f"\n{'='*60}")
    print(f"Overall Summary: {total_processed}/{total_papers} papers processed successfully")
    if total_errors > 0:
        print(f"Errors: {total_errors} papers failed")
    print(f"{'='*60}")


if __name__ == "__main__":
    process_all_question_papers()
