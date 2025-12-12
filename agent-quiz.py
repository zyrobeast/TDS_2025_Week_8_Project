from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import requests
import os
import subprocess
from dataclasses import dataclass, field
from typing import List
from pydantic import BaseModel, field_validator
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.usage import UsageLimits

from playwright.async_api import async_playwright

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EMAIL = os.getenv("EMAIL")
SECRET = os.getenv("SECRET")
AI_PIPE_TOKEN = os.getenv("AI_PIPE_TOKEN")
OUTPUT_FILE_PATH = "run.py"
MAX_RETRIES = 2

@dataclass
class AgentDeps:
    question_data: str
    previous_mistakes: List[str] = field(default_factory=list)


model = OpenAIResponsesModel(
    "gpt-4o-mini",
    provider=OpenAIProvider(
        base_url="https://aipipe.org/openai/v1/",
        api_key=AI_PIPE_TOKEN
    )
)

agent = Agent(model, retries=3, deps_type=AgentDeps)


@agent.system_prompt
async def add_task(ctx: RunContext[AgentDeps]) -> str:
    return f"""
    You are a quiz solver who can use Python if necessary.
    Solve the question shown below.

    {ctx.deps.question_data}

    You must:
    - Provide ONLY Python code (no explanation text)
    - The secret, email are environment variables and the question url is passed to the python script as arguement.
    - Code must solve the question
    {'\n'.join('- {mistake}' for mistake in ctx.deps.previous_mistakes)}
    - Code must POST the answer to the URL included in the question and print the response on the standard output.
    - At the end, call the tool to run the code using 'uv'

    Output ONLY the code or the output of any tool — no markdown, no text.
    """


@agent.tool_plain
def write_code(file_data: str):
    """Creates run.py and writes the generated code into it."""
    with open(OUTPUT_FILE_PATH, "w") as writer:
        writer.write(file_data)


@agent.tool_plain
def run_task(dependencies: List[str]):
    """
    Uses uv package manager to install dependencies temporarily
    and run run.py.
    """
    try:
        result = subprocess.run(
            ["uv", *' '.join(f'--with {d}' for d in dependencies).split(), "python", "run.py"],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        return e.stderr
    except PermissionError:
        print("Permission Error")
        return "Permission Error"
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return f"Unexpected error: {str(e)}"


@app.get("/")
async def root():
    return {
        "author": "zyrobeast",
        "endpoints": [
            {
                "endpoint": "/",
                "methods": ["POST"],
                "description": (
                    "Submit a task that requires solving/rendering a problem "
                    "(e.g. captcha, dynamic quiz). The system processes the URL "
                    "by rendering it in a browser and solving the extracted problem."
                ),
                "body_format": {
                    "email": {"type": "string"},
                    "secret": {"type": "string"},
                    "url": {"type": "string"},
                    "..other fields..": "Any additional data allowed"
                }
            }
        ]
    }


async def extract_question(url: str) -> str:
    """
    Load the given URL using Playwright, render the JavaScript,
    and extract the visible text as question_data.
    """
    async with async_playwright() as pw:
        browser = await pw.firefox.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        text = await page.inner_text("body")

        await browser.close()
        return text

async def solve_question(url: str, mistakes=None) -> str:
    if mistakes is None:
        mistakes = []

    try:
        question_data = await extract_question(url)
    except Exception as e:
        print("Playwright extraction error:", e)
        return JSONResponse(status_code=500, content={"error": "Failed to extract question"})

    try:
        result = await agent.run(
            deps=AgentDeps(question_data=question_data, previous_mistakes=mistakes),
            usage_limits=UsageLimits(tool_calls_limit=5)
        )
        
        result_str = agent.output
    except Exception as e:
        print("Agent execution error:", e)
        return "Some error occurred"

    try:
        result_json = json.loads(result_str)
    except json.JSONDecodeError:
        print("Result is not valid JSON:", result_str)
        return "Invalid response from agent"


    if not result_json.get("correct", False) and len(mistakes) < MAX_RETRIES:
        mistakes.append(result_json.get("reason", "Unknown mistake"))
        return await solve_question(url, mistakes)

    
    if "url" in result_json:
        return await solve_question(result_json["url"], mistakes=[])

    return json.dumps(result_json)

        

@app.post("/")
async def task_root(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})

    email = payload.get("email")
    secret = payload.get("secret")
    url = payload.get("url")

    if not email or not secret or not url:
        return JSONResponse(status_code=400, content={"error": "Missing required fields"})

    if secret != SECRET or email.lower() != EMAIL.lower():
        return JSONResponse(status_code=403, content={"error": "Invalid secret or email."})

    background_tasks.add_task(solve_question, url)
    return JSONResponse(status_code=200, content={"status": "queued"})


if __name__ == "__main__":
    uvicorn.run(app, port=7860, host="0.0.0.0")
