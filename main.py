import os
from subprocess import PIPE, Popen
from typing import Optional

import markdown2
import pip._vendor.tomli as tomllib
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
from utils import delete_audio_file, get_IPA, get_synonyms, tts_edge

app = FastAPI()

app.mount("/audio", StaticFiles(directory="./audio"), name="audio")

app.mount("/static", StaticFiles(directory="./static"), name="static")

STYLE_SNIPPET = """\
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="/static/style.css"/>
<script src="/static/script.js"></script>
<link rel="icon" type="image/x-icon" href="/static/favicon.ico">
<link rel="stylesheet" href="/static/markdown7.css"
    media="screen and (min-width: 600px)"
/>
<link rel="stylesheet" href="/static/markdown.css"
    media="screen and (max-width: 640px)"
/>
<link rel="stylesheet" href="/static/md-editor.min.css">
<script src="/static/md-editor.min.js"></script>
"""

with open("config.toml") as fp:
    toml_config = tomllib.load(fp)
    NOTES_FOLDER = toml_config["notes_folder"]
    # NOTES_FOLDER = "/home/sakana/Learning-for-IELTS/"


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


@app.get("/static/{file_name}", include_in_schema=False)
async def static_file(file_name):
    return FileResponse(f"./static/{file_name}")


@app.get("/audio/{file_name}")
async def get_audio(file_name: str):
    return FileResponse(f"./audio/{file_name}")


def generate_tree(path, html=""):
    for file in os.listdir(path):
        rel = path + "/" + file
        if os.path.isdir(rel):
            html += (
                "<p class='toggle'>%s</p><div class='child' hidden='true'>"
                % (file)
            )
            html += generate_tree(rel)
            html += "</div>"
        else:
            html += "<p>%s</p>" % (file)
    return html


@app.get("/notes/{rest_of_path:path}", response_class=HTMLResponse)
async def notes(rest_of_path: str) -> str:
    file_path = NOTES_FOLDER + rest_of_path
    toc_html = ""
    if os.path.isdir(file_path):
        proc = Popen(
            args=["tree", "-H", "./", file_path],
            stdout=PIPE,
            universal_newlines=True,
        )
        stdout, _ = proc.communicate()
        note_html = stdout
    else:
        try:
            with open(file_path) as note_file:
                text = note_file.read()
                note_html = markdown2.markdown(
                    text,
                    extras=["strike", "tables", "toc", "fenced-code-blocks"],
                )
                toc_html = note_html.toc_html
        except:
            note_html = "Unable to read the file"
    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>{rest_of_path.split("/")[-1]}</title>
            {STYLE_SNIPPET}
        </head>
        <body>
            <a href="/notes/">Notes Tree</a>&nbsp&nbsp&nbsp&nbsp&nbsp
            <a href="/">Dictionary</a>&nbsp&nbsp&nbsp&nbsp&nbsp
            <hr>
            <div><p>Table of Content</p>{toc_html}</div>
            <p>{note_html}</p>
        </body>
        </html>
    """
    return html


@app.get("/tts_question/{qid}")
async def tts_question(qid: int):
    question = db_get_question_by_id(qid)
    if not question:
        return "No question"
    tts_edge(question)
    return "ok"


@app.get("/show_synonyms/{qid}", response_class=HTMLResponse)
async def show_synonyms(qid: int):
    question = db_get_question_by_id(qid)
    if not question:
        return "No question"
    question_text = question.text
    if " - " in question_text:
        q_text = question_text.split(" - ")[-1]
    else:
        q_text = question_text
    if " " in q_text:
        return "This feature is only for words"
    word = q_text
    synonyms = get_synonyms(word)
    all_qs = db_get_all_question()
    q_texts = []
    for question in all_qs:
        question_text = question.text
        if "When i ask you a word" in question_text:
            continue
        if " - " in question_text:
            q_text = question_text.split(" - ")[-1]
        else:
            q_text = question_text
        if q_text in synonyms:
            q_texts.append((q_text, question.id))

    syns_html = "".join([f"<p>{syn}</p>" for syn in synonyms])

    syns_in_db_html = (
        "".join(
            [
                f'<p><a href="/question/{qid}"  style="text-decoration: none;">{qt.strip()}</a></p>'
                for qt, qid in q_texts
            ]
        )
        or "None"
    )

    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>Synonyms of {word}</title>
            {STYLE_SNIPPET}
        </head>
        <body>
            <h1>Synonyms</h1>
            <h2>In database</h2>
            {syns_in_db_html}
            <h2>All</h2>
            {syns_html}
        </body>
        </html>
        """
    return html


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    questions = db_get_all_question()
    questions = [q for q in questions if not q.is_hidden]
    questions_count = len(questions)
    trs = []
    if request.query_params.get("sort") == "length":
        questions = sorted(questions, key=lambda q: len(q.text))
    show_example = False
    if request.query_params.get("example") == "true":
        show_example = True
    questions_only = False
    if request.query_params.get("questions_only") == "true":
        questions_only = True

    for question in questions:
        audio_src = f"/audio/{question.id}.mp3"
        question_text = question.text
        if "When i ask you a word" in question_text:
            continue
        if " - " in question_text:
            q_text = question_text.split(" - ")[-1]
            q_context = question_text.split(" - ")[0]
        else:
            q_context = ""
            q_text = question_text

        example = question.example if question.example else ""
        tr = (
            '<tr><td><label class="unselectable"> - </label><a style="text-decoration: none;"'
            f' href="/question/{question.id}">{q_text!s} </a></td>'
            # f"<td>{q_context}</td>"
            f"{'<td>' + q_context + '</td>' if not questions_only else ''}"
            f"{'<td>' + example + '</td>' if show_example else ''}"
            # f'<td><button play-id="{question.id}" class="playButton">Listen</button></td>'
            f'<td><button onclick="deleteQuestionMainPage(this, {question.id})">Delete</button></td></tr>'
        )
        trs.append(tr)
    trs_html = "".join(trs)
    sort_link_url = "/?sort=length"
    show_example_link = "/?example=true"
    questions_only_link = "/?questions_only=true"
    sort_link = (
        '<a href="#bottom"  style="text-decoration: none;">Go to Bottom</a>'
        f' &nbsp&nbsp&nbsp&nbsp&nbsp<a href="{sort_link_url}"'
        ' style="text-decoration: none;">Sort by Length</a>'
        f' &nbsp&nbsp&nbsp&nbsp&nbsp<a href="{show_example_link}"'
        ' style="text-decoration: none;">Show Examples</a>'
        f' &nbsp&nbsp&nbsp&nbsp&nbsp<a href="{questions_only_link}"'
        ' style="text-decoration: none;">Questions Only</a>'
        '&nbsp&nbsp&nbsp&nbsp&nbsp<a href="/notes/">Notes Tree</a>'
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
            {STYLE_SNIPPET}
        </head>
        <body>
            <h1 id="top"><a href="/" style="text-decoration: none";>{questions_count} Questions</a></h1>
            <p>{sort_link}</p>
            <p>{add_question_link}</p>
            <table border="1">
            <tr>
                <th>Question</th>
                {"<th>Context</th>" if not questions_only else ""}
                {"<th>Examples</th>" if show_example else ""}
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
        <a href="#" class="float hide-on-desktop">
            <i class="my-float" style="font-size:20px">top</i>
        </a>
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
        <textarea name="question_text">{question.text}</textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Question</title>
        {STYLE_SNIPPET}
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
    # Only display the first answer
    answer_div = ""
    if question.answers:
        a = question.answers[0]
        answer_div = (
            '<div id="answer-div">'
            f"{markdown2.markdown(a.text, extras=['strike'])}"
            f"""<button onclick="location.href='/edit_answer/{a.id}'" type="button">Edit</button>"""
            "&nbsp&nbsp&nbsp"
            '<button onclick="deleteAnswer(this,'
            f' {a.id})">Delete</button>'
            "</div>"
        )
    audio_src = f"/audio/{question_id}.mp3"
    word = question.text.split(" - ")[-1].strip()
    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>{word.capitalize()}</title>
            {STYLE_SNIPPET}
        </head>
        <body>
            <a href="/">Back to Main Page</a>&nbsp&nbsp&nbsp&nbsp&nbsp
            <a href="/add_question">Add Question</a>
            <h1>Question and Answers</h1>
            <h2>Question:</h2>
            <p id="question">{question.text}</p>
            <button onclick="location.href='/edit_question/{question_id}'" type="button">Edit</button>
            <button onclick="deleteQuestion({question_id})" type="button" id="dbt">Delete</button>
            <hr>
            <p>
            /{get_IPA(word)}/
            <audio id="1st-ipa-audio" controls style="display: none;"
                oncanplay="myOnCanPlayFunction()"
                >
                <source src="{f"https://ssl.gstatic.com/dictionary/static/sounds/oxford/{word}--_us_1.mp3"}" type="audio/mp3">
                <source src="{f"https://ssl.gstatic.com/dictionary/static/sounds/oxford/x{word}--_us_1.mp3"}" type="audio/mp3">
            </audio>
            <audio id="2nd-ipa-audio" controls style="display: none;"
                oncanplay="myOnCanPlayFunction()"
                >
                <source id="2nd-ipa-source" src="{f"https://ssl.gstatic.com/dictionary/static/sounds/oxford/{word}--_us_2.mp3"}" type="audio/mp3">
            </audio>
            </p>
            <hr>
            <div id="tts-div" style="display: none;">
            <audio controls class="svelte-eemfgq" oncanplay="ttsCanPlay()">
                <source src="{audio_src}" type="audio/mp3">
            </audio>
            <button onclick="deleteAudio({question_id})" type="button">Delete audio</button>
            <hr>
            </div>
            <button onclick="playEdgeTTS(this, {question_id})" type="button">Play Edge TTS</button>
            <hr>
            <h2>Answers:</h2>
            <button onclick="location.href='/add_answer?qid={question_id}'" type="button">Add answer</button>
                {answer_div}
            <script>var questionId = "{question_id}"</script>
            <h2>Example:</h2>
            <p>{markdown2.markdown(question.example or "", extras=['strike', 'tables'])}</p>
            <button onclick="location.href='/edit_example/{question_id}'" type="button" id="edit-example">
            Edit example</button>
            <h2>Synonyms:</h2>
            <a href='/show_synonyms/{question_id}'>Show synonyms</a>
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
        <textarea name="answer_text">{answer.text}</textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Answer</title>
        {STYLE_SNIPPET}
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
        <textarea name="example_text">{question.example or ""}</textarea><br>
        <input type="submit" value="Submit" class="submit-button">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Example</title>
        {STYLE_SNIPPET}
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
        <textarea name="question_text"></textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add Question</title>
        {STYLE_SNIPPET}
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
        <textarea name="answer_text"></textarea><br>
        <input value="{qid}" name="question_id" type="hidden">
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Answer</title>
        {STYLE_SNIPPET}
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
