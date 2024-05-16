from typing import Optional

import markdown2
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from database import (
    db_add_answer,
    db_add_question,
    db_delete_answer,
    db_delete_question,
    db_get_all_question,
    db_get_answer_by_id,
    db_get_question_by_id,
    db_update_answer_text,
    db_update_example,
    db_update_question_text,
)
from utils import delete_audio_file

app = FastAPI()

app.mount("/audio", StaticFiles(directory="./audio"), name="audio")


FAVICON_PATH = "./static/favicon.ico"
MANIFEST_PATH = "./static/manifest.ico"
SCRIPT_PATH = "./static/script.js"

MOBILE_STYLE_SNIPPET = """\
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-size: 19px;
            font-family: sans-serif;
        }
        @media only screen and (max-width: 600px) {
            body {
                font-size: 17px;
                font-family: sans-serif;
            }
        }
        button {font-size: 15px;}
        audio.svelte-eemfgq {
            padding: 8px;
            width: 100%;
            height: 56px;
        }
        textarea {
            height: 18em;
            width: 70em;
            font-size: 16px;
            font-family: sans-serif;
            }
    </style>
    <script src="/script.js"></script>
"""


class EditAnswerForm(BaseModel):
    answer_text: str

    @classmethod
    def as_form(cls, answer_text: str = Form(...)):
        return cls(answer_text=answer_text)


class EditQuestionForm(BaseModel):
    question_text: str

    @classmethod
    def as_form(cls, question_text: str = Form(...)):
        return cls(question_text=question_text)


class EditExampleForm(BaseModel):
    example_text: Optional[str] = Field(default="", description="Example text")

    @classmethod
    def as_form(cls, example_text: str = Form(None)):
        return cls(example_text=example_text)


class AddQuestionForm(BaseModel):
    question_text: str

    @classmethod
    def as_form(cls, question_text: str = Form(...)):
        return cls(question_text=question_text)


class AddAnswerForm(BaseModel):
    answer_text: str
    question_id: int

    @classmethod
    def as_form(
        cls, answer_text: str = Form(...), question_id: int = Form(...)
    ):
        return cls(answer_text=answer_text, question_id=question_id)


def shorten_string(s, max_length=180):
    if len(s) <= max_length:
        return s
    else:
        return s[: max_length - 3] + "..."


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_file():
    return FileResponse(FAVICON_PATH)


@app.get("/manifest.json", include_in_schema=False)
async def manifest_file():
    return FileResponse(MANIFEST_PATH)


@app.get("/script.js", include_in_schema=False)
async def script_file():
    return FileResponse(SCRIPT_PATH)


@app.get("/audio/{file_name}")
async def get_audio(file_name: str):
    return FileResponse(f"./audio/{file_name}")


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    questions = db_get_all_question()
    questions = [q for q in questions if not q.is_hidden]
    questions_count = len(questions)
    trs = []
    if request.query_params.get("sort") == "length":
        questions = sorted(questions, key=lambda q: len(q.text))
    for question in questions:
        audio_src = f"/audio/{question.id}.mp3"
        question_text = question.text
        if "When i ask you a word" in question_text:
            continue
        if " - " in question_text:
            q_text = question_text.split(" - ")[-1]
            q_context = question_text.split(" - ")[0]
        else:
            q_context = q_text = question_text
        tr = (
            '<tr><td> - <a style="text-decoration: none;"'
            f' href="/question/{question.id}">{q_text!s} </a></td>'
            f"<td>{q_context}</td>"
            # f'<td><button play-id="{question.id}" class="playButton">Listen</button></td>'
            f'<td><button onclick="deleteQuestionMainPage(this, {question.id})">Delete</button></td></tr>'
        )
        trs.append(tr)
    trs_html = "".join(trs)
    sort_link_url = "/?sort=length"
    sort_link = (
        '<a href="#bottom"  style="text-decoration: none;">Go to Bottom</a>'
        f' &nbsp&nbsp&nbsp&nbsp&nbsp<a href="{sort_link_url}"'
        ' style="text-decoration: none;">Sort by Length</a>'
    )
    add_question_link = (
        '<a href="/add_question" style="text-decoration: none;">Add'
        " Question</a>"
    )

    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dictionary</title>
            <link rel="icon" type="image/x-icon" href="/favicon.ico">
            {MOBILE_STYLE_SNIPPET}
        </head>
        <body>
            <h1 id="top"><a href="/" style="text-decoration: none";>{questions_count} Questions</a></h1>
            <p>{sort_link}</p>
            <p>{add_question_link}</p>
            <table border="1">
            <tr>
                <th>Question</th>
                <th>Context</th>
                <th>Action</th>
            </tr>
                {trs_html}
            </table>
            <div id="bottom">
            <p>
            <a href="/add_question" style="text-decoration: none;">Add Question
            </a>
            </p>
                <p><a href="#top"  style="text-decoration: none;">Go to Top</a></p>
            </div>
        </body>
        </html>
        """
    return html


@app.get("/edit_question/{question_id}", response_class=HTMLResponse)
async def edit_question_page(question_id: int):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"
    form_html = f"""\
    <form method="post" action="/edit_question/{question_id}">
        <textarea class="submit-on-shift-enter" name="question_text">{question.text}</textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Question</title>
        {MOBILE_STYLE_SNIPPET}
    </head>
    <body>
        <h1>Edit Question</h1>
        {form_html}
    </body>
    </html>
    """
    return html


@app.post("/edit_question/{question_id}", response_class=HTMLResponse)
async def edit_question(
    question_id: int,
    form_data: EditQuestionForm = Depends(EditQuestionForm.as_form),
):
    updated_text = form_data.question_text
    try:
        if q_id := db_update_question_text(question_id, updated_text):
            return RedirectResponse(url=f"/question/{q_id}", status_code=303)
    except IntegrityError:
        return "Question text UNIQUE constraint failed"


@app.get("/question/{question_id}", response_class=HTMLResponse)
async def question_page(question_id: int):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"
    answers_li_html = "".join(
        [
            f"<li>{markdown2.markdown(a.text, extras=['strike'])}"
            f"""<button onclick="location.href='/edit_answer/{a.id}'" type="button">Edit</button>"""
            "&nbsp&nbsp&nbsp"
            '<button onclick="deleteAnswer(this,'
            f' {a.id})">Delete</button></li>'
            for a in question.answers
        ]
    )
    audio_src = f"/audio/{question_id}.mp3"

    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>Definition</title>
            {MOBILE_STYLE_SNIPPET}
        </head>
        <body>
            <a href="/">Back to Questions</a>&nbsp&nbsp&nbsp&nbsp&nbsp
            <a href="/add_question">Add Question</a>
            <h1>Question and Answers</h1>
            <h2>Question:</h2>
            <p id="question">{question.text}</p>
            <button onclick="location.href='/edit_question/{question_id}'" type="button">Edit</button>
            <button onclick="deleteQuestion({question_id})" type="button">Delete</button>
            <div>
            <audio controls class="svelte-eemfgq">
                <source src="{audio_src}" type="audio/mp3">
            </audio>
            </div>
            <button onclick="deleteAudio({question_id})" type="button">Delete audio</button>
            <h2>Answers:</h2>
            <button onclick="location.href='/add_answer?qid={question_id}'" type="button">Add answer</button>
            <ul id="answer-ul">
                {answers_li_html}
            </ul>
            <form method="post" action="/add_answer" style="display:none" id="hidden-a-form">
                <textarea class="submit-on-shift-enter" name="answer_text"></textarea><br>
                <input value="{question_id}" name="question_id" type="hidden">
                <input type="submit" value="Submit">
            </form>
            <h2>Example:</h2>
            <button onclick="location.href='/edit_example/{question_id}'" type="button">Edit example</button>
            <p>{markdown2.markdown(question.example or "", extras=['strike'])}</p>
            <br><br><br><br>
        </body>
        </html>
        """
    return html


@app.get("/delete_question/{question_id}", response_class=HTMLResponse)
async def delete_question(question_id: int):
    db_delete_question(question_id)
    return "200"


@app.get("/delete_audio/{question_id}", response_class=HTMLResponse)
async def delete_audio(question_id: int):
    delete_audio_file(question_id)
    return "200"


@app.get("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer_page(answer_id: int):
    # Replace this with your actual function to fetch answer by ID
    answer = db_get_answer_by_id(answer_id)
    if not answer:
        return "404"
    form_html = f"""\
    <form method="post" action="/edit_answer/{answer_id}">
        <textarea class="submit-on-shift-enter" name="answer_text">{answer.text}</textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Answer</title>
        {MOBILE_STYLE_SNIPPET}
    </head>
    <body>
        <h1>Edit Answer</h1>
        {form_html}
    </body>
    </html>
    """
    return html


@app.post("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer(
    answer_id: int, form_data: EditAnswerForm = Depends(EditAnswerForm.as_form)
):
    updated_text = form_data.answer_text
    if question_id := db_update_answer_text(answer_id, updated_text):
        return RedirectResponse(url=f"/question/{question_id}", status_code=303)


@app.get("/edit_example/{question_id}", response_class=HTMLResponse)
async def edit_example_page(question_id: int):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"
    form_html = f"""\
    <form method="post" action="/edit_example/{question_id}" class="answer-form">
        <textarea class="submit-on-shift-enter" name="example_text">{question.example or ""}</textarea><br>
        <input type="submit" value="Submit" class="submit-button">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Example</title>
        {MOBILE_STYLE_SNIPPET}
    </head>
    <body>
        <h1>Edit Example</h1>
        {form_html}
    </body>
    </html>
    """
    return html


@app.post("/edit_example/{question_id}", response_class=HTMLResponse)
async def edit_example(
    question_id: int,
    form_data: EditExampleForm = Depends(EditExampleForm.as_form),
):
    print(form_data.example_text)
    if not (updated_text := form_data.example_text):
        updated_text = ""
    if returned_qid := db_update_example(question_id, updated_text):
        return RedirectResponse(
            url=f"/question/{returned_qid}", status_code=303
        )


@app.get("/delete_answer/{answer_id}", response_class=HTMLResponse)
async def delete_answer(answer_id: int):
    if question_id := db_delete_answer(answer_id):
        return RedirectResponse(url=f"/question/{question_id}", status_code=303)


@app.get("/add_question", response_class=HTMLResponse)
async def add_question_page():
    form_html = f"""\
    <form method="post" action="/add_question">
        <textarea class="submit-on-shift-enter" name="question_text"></textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add Question</title>
        {MOBILE_STYLE_SNIPPET}
    </head>
    <body>
        <h1>Add Question</h1>
        {form_html}
    </body>
    </html>
    """
    return html


@app.post("/add_question", response_class=HTMLResponse)
async def add_question(
    form_data: AddQuestionForm = Depends(AddQuestionForm.as_form),
):
    updated_text = form_data.question_text
    try:
        if q_id := db_add_question(updated_text):
            return RedirectResponse(url=f"/question/{q_id}", status_code=303)
    except IntegrityError:
        return "Question text UNIQUE constraint failed"


@app.get("/add_answer", response_class=HTMLResponse)
async def add_answer_page(qid: int):
    # Replace this with your actual function to fetch answer by ID
    form_html = f"""\
    <form method="post" action="/add_answer">
        <textarea class="submit-on-shift-enter" name="answer_text"></textarea><br>
        <input value="{qid}" name="question_id" type="hidden">
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Answer</title>
        {MOBILE_STYLE_SNIPPET}
    </head>
    <body>
        <h1>Edit Answer</h1>
        {form_html}
    </body>
    </html>
    """
    return html


@app.post("/add_answer", response_class=HTMLResponse)
async def add_answer(
    form_data: AddAnswerForm = Depends(AddAnswerForm.as_form),
):
    updated_text = form_data.answer_text
    qid = form_data.question_id
    if question := db_get_question_by_id(qid):
        db_add_answer(updated_text, question=question)
        return RedirectResponse(url=f"/question/{qid}", status_code=303)
    return "Question doesn't exist"
