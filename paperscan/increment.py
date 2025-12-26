from dotenv import load_dotenv
import google.generativeai as genai
import re 
import os
from pymongo import MongoClient
import json
from pymongo import MongoClient
load_dotenv()


MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION_SYLLABUS = os.getenv("MONGO_COLLECTION_SYLLABUS")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]


def get_extracted_syllabus(course_syllabus):
    return course_syllabus["extracted_syllabus"]["modules"]


def split_topics(topics):
    parts = re.split(r"[-–—]", topics)
    return [p.strip() for p in parts if p.strip()]


def clean_topics():
    course_syllabus = db[MONGO_COLLECTION_SYLLABUS].find_one(
    {"course_code": "BITE303L"}
)

    modules = get_extracted_syllabus(course_syllabus)

    for module in modules:
       topics_blob = module["topics"][0]
       topic_in_module = split_topics(topics_blob)
       print("MODULE:", module["module_number"], topic_in_module)

