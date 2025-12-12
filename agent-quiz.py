from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import requests
import os
import json
import subprocess
from dataclasses import dataclass, field
from typing import List
from pydantic import BaseModel, field_validator
from pydantic_ai import Agent, RunContext, ModelRetry
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
AGENT_USE_LEFT = 5

@dataclass
class AgentDeps:
    question_dict: dict = field(default_factory=dict)
    submission_responses: List[str] = field(default_factory=list)

model = OpenAIResponsesModel(
    "gpt-4o-mini",
    provider=OpenAIProvider(
        base_url="https://aipipe.org/openai/v1/",
        api_key=AI_PIPE_TOKEN
    ))

agent = Agent(model, retries=3, deps_type=AgentDeps)

@agent.system_prompt
async def add_task(ctx: RunContext[AgentDeps]) -> str:
    return f"""
    You are a quiz solver who can use Python programming language if necessary.
    Solve the question given in the url given in the json below. The question might be hidden in text of the page, in audio, image or video. Write python code appropriately to extract the question if necessary.
    
    {json.dumps(ctx.deps.question_dict, indent=2)}

    You must:
    - Write a python code that prints the answer to the question only to the output stream. You may run multiple python scripts if you need to analyse something in the given page.
    - Code must solve the question given in the url page.
    - Do not try to submit the answer in the code, use the submit_answer tool.
    - Execute the code using the tool provided to get the answer.
    - Submit the result of the code to the submission url given in the question page. The result may contain errors, handle them appropriately.
    - Return the submission response from the submission tool as the final output (Output text, no markdown).
    """

@agent.tool_plain
async def load_page_html(url: str) -> str:
    """
    Load given URL using Playwright, render JavaScript,
    and return the fully rendered page HTML.
    """
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = browser.new_context(accept_downloads=False)
            page = context.new_page()

            await page.goto(url, wait_until="networkidle", timeout=30000)

            html_content = await page.content()
            await browser.close()
            print("\n\nLoaded page HTML:\n", html_content, "\n\n")
            return html_content
    except Exception as e:
        print("Playwright error:", e)
        raise ModelRetry("Failed to use Playwright to load the page. Try again.")

@agent.tool_plain
async def write_code_and_get_result(file_data: str, dependencies: List[str]):
    """
    Creates run.py and writes the generated code into it.
    Then uv package manager is used to install dependencies of the file temporarily and run run.py.
    Finally, the output printed by run.py on the the output stream is used as return value of the tool.
    Any error is also captured and returned.
    """
    with open(OUTPUT_FILE_PATH, "w") as writer:
        writer.write(file_data)
        print("\n------------Python code ------------\n", file_data)

    print("\n\nRunning task with dependencies:", dependencies)

    try:
        result = subprocess.run(
            ["uv", *' '.join(f'--with {d}' for d in dependencies).split(), "run", "run.py"],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        return result.stdout
    except Exception as e:
        print(f"Code execution failed due to:\n {str(e)}")
        raise ModelRetry(f"Code execution failed due to:\n {str(e)}")

@agent.tool
async def submit_answer(ctx: RunContext[AgentDeps], submit_url: str, question_url: str, answer: str) -> str:
    """
    Submit the answer for the question_url to the given submit_url via POST request.
    Returns the response json.
    """
    try:
        json_data = {}
        json_data['secret'] = SECRET
        json_data['email'] = EMAIL
        json_data['url'] = question_url
        json_data['answer'] = answer
        response = requests.post(submit_url, json=json_data, timeout=20)
        response_json = response.json()

        print("\nResponse:", response_json)
        ctx.deps.submission_responses.append(response_json)
        if not response_json.get("correct", False):
            raise ModelRetry(f"Answer was incorrect, please try rewriting the code. Reason for incorrect answer: {response_json.get('reason', 'Unknown')}. If the answer is incorrect multiple times, output {response_json} as the result.")
        
        return response_json
    except Exception as e:
        print("Error submitting answer:", e)
        raise ModelRetry( f"Error submitting answer: {str(e)}\n. Please try again.")

def get_question_fields(question_json):
    return {key: value for key, value in question_json.items() if key not in ["email", "secret", "correct", "reason"]}

async def solve_question(question_fields: dict, submission_responses: List[str]) -> str:
    global AGENT_USE_LEFT
    print(question_fields, f"\n\nAGENT_USE_LEFT: {AGENT_USE_LEFT}", )

    try:
        result = await agent.run(
            deps=AgentDeps(question_dict=question_fields, submission_responses=submission_responses),
            usage_limits=UsageLimits(tool_calls_limit=10)
        )
        
        result_str = result.output
        print("\nFinal agent output:", result_str)
    except Exception as e:
        print("Agent execution error:", e)

    if submission_responses and "url" in submission_responses[-1] and AGENT_USE_LEFT > 0:
        await solve_question(get_question_fields(submission_responses[-1]), submission_responses)
        AGENT_USE_LEFT -= 1

    return "Execution completed"

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

@app.post("/")
async def task_root(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})

    print(payload)

    email = payload.get("email")
    secret = payload.get("secret")
    url = payload.get("url")

    if not email or not secret or not url:
        return JSONResponse(status_code=400, content={"error": "Missing required fields"})

    if secret != SECRET or email.lower() != EMAIL.lower():
        return JSONResponse(status_code=403, content={"error": "Invalid secret or email."})

    global AGENT_USE_LEFT
    if AGENT_USE_LEFT > 0:
        background_tasks.add_task(solve_question, get_question_fields(payload), [])
        AGENT_USE_LEFT -= 1
        return JSONResponse(status_code=200, content={"status": "queued"})
    else:
        return JSONResponse(status_code=429, content={"error": "Agent usage limit reached. Try again later."})


if __name__ == "__main__":
    uvicorn.run(app, port=7860, host="0.0.0.0")
