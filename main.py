import os
from fastapi import FastAPI
from dotenv import load_dotenv
from supabase import create_client, Client


app = FastAPI()

supabase: Client = create_client(
    supabase_url = os.getenv("SUPABASE_URL"),
    supabase_key = os.getenv("SUPABASE_PUBLISHABLE_KEY")
)


@app.route('/')
def index():
    