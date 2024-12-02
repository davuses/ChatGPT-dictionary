import os
import re
from subprocess import PIPE, Popen
from typing import Optional

import markdown2
import tomllib
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
    db_question_increment_visit_number,
    db_question_last_visit_old_enough,
    db_update_answer_text,
    db_update_example,
    db_update_question_text,
)
from utils import (
    delete_audio_file,
    from_last_visit,
    get_all_words,
    get_IPA,
    get_synonyms,
    tts_edge,
)

app = FastAPI()

app.mount("/audio", StaticFiles(directory="./audio"), name="audio")

app.mount("/static", StaticFiles(directory="./static"), name="static")

templates = Jinja2Templates(directory="templates")


STYLE_SNIPPET = """\
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="/static/style.css"/>
<script src="/static/script.js"></script>
<link rel="icon" type="image/x-icon" href="/static/favicon.ico">
<link rel="stylesheet" href="/static/markdown-pc.css"
    media="screen and (min-width: 600px)"
/>
<link rel="stylesheet" href="/static/markdown-mobile.css"
    media="screen and (max-width: 640px)"
/>
<link rel="stylesheet" href="/static/md-editor.min.css">
<script src="/static/md-editor.min.js"></script>
"""

with open("config.toml", "rb") as fp:
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


@app.get("/notes/{rest_of_path:path}", response_class=HTMLResponse)
async def notes(rest_of_path: str, request: Request):
    file_path = NOTES_FOLDER + rest_of_path
    toc_html = ""
    is_dir = os.path.isdir(file_path)
    if is_dir:
        proc = Popen(
            args=[
                "tree",
                "-I",
                "*.png",
                "-I",
                "*.jpg",
                "-I",
                "*.webp",
                "-I",
                "Media",
                "-H",
                "./",
                file_path,
            ],
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
    title = rest_of_path.split("/")[-1]
    toc_exist = bool(toc_html)
    context = {
        "title": title,
        "toc_html": toc_html,
        "note_html": note_html,
        "is_dir": is_dir,
        "toc_exist": toc_exist,
    }
    return templates.TemplateResponse(
        request=request, name="notes.html.jinja", context=context
    )


@app.get("/tts_question/{qid}")
async def tts_question(qid: int):
    question = db_get_question_by_id(qid)
    if not question:
        return "No question"
    tts_edge(question)
    return "ok"


@app.get("/show_synonyms/{qid}", response_class=HTMLResponse)
def show_synonyms(qid: int, request: Request):
    question = db_get_question_by_id(qid)
    if not question:
        return "No question"
    question_text: str = question.text
    if " - " in question_text:
        word = question_text.split(" - ")[-1]
    else:
        word = question_text
    if " " in word:
        return "This feature is for words only"
    all_words = get_all_words()
    thesauruses = []
    if synonyms_data := get_synonyms(word):
        for synonym_data in synonyms_data:
            synonyms = synonym_data[3]
            w_strings = []
            for syn in synonyms:
                if qids := all_words.get(syn):
                    w_template = '<a href="/question/{}" style="text-decoration: none;">{}</a>'
                    w_string = " / ".join(
                        [w_template.format(qid, syn) for qid in qids]
                    )
                else:
                    w_string = syn
                w_strings.append(w_string)
            synonyms_html = ", ".join(w_strings)
            meaning_md = re.sub(
                r"as in (.+?):(.+)",
                lambda match: f"as in *{match.group(1)}*:\n\n{match.group(2)}",
                synonym_data[2],
            )
            thesauruses.append(
                (synonym_data[1], markdown2.markdown(meaning_md), synonyms_html)
            )
    synonyms_exist = bool(synonyms_data)

    context = {
        "qid": qid,
        "word": word,
        "synonyms_exist": synonyms_exist,
        "thesauruses": thesauruses,
    }
    return templates.TemplateResponse(
        request=request, name="synonyms.html.jinja", context=context
    )


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    questions = db_get_all_question()
    questions_count = len(questions)
    show_example = request.query_params.get("example") == "true"
    questions_only = request.query_params.get("questions_only") == "true"
    q_tuples: list[tuple] = []
    # (question.id, q_text, q_context, example)
    for question in questions:
        question_text = question.text
        if "When i ask you a word" in question_text:
            continue
        q_context = ""
        q_text = question_text
        if " - " in question_text:
            q_text = question_text.split(" - ")[-1].strip()
            q_context = question_text.split(" - ")[0]

        example = question.example or ""
        q_tuples.append((question.id, q_text, q_context, example))

    context = {
        "questions_count": questions_count,
        "q_tuples": q_tuples,
        "question_only": questions_only,
        "show_example": show_example,
    }
    return templates.TemplateResponse(
        request=request, name="root.html.jinja", context=context
    )


@app.get("/edit_question/{question_id}", response_class=HTMLResponse)
async def edit_question_page(question_id: int, request: Request):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"

    context = {"question_id": question_id, "question_text": question.text}
    return templates.TemplateResponse(
        request=request, name="edit_question.html.jinja", context=context
    )


@app.post("/edit_question/{question_id}", response_class=HTMLResponse)
async def edit_question(
    question_id: int,
    form_data: EditQuestionForm = Depends(EditQuestionForm.as_form),
):
    updated_text = form_data.question_text
    updated_text = updated_text.strip()
    try:
        if q_id := db_update_question_text(question_id, updated_text):
            return RedirectResponse(url=f"/question/{q_id}", status_code=303)
    except IntegrityError:
        return "Question text UNIQUE constraint failed"


@app.get("/question/{question_id}", response_class=HTMLResponse)
async def question_page(question_id: int, request: Request):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"
    how_long_ago = (
        from_last_visit(last_visit)
        if (last_visit := question.last_visit)
        else "None"
    )
    if db_question_last_visit_old_enough(question.id):
        db_question_increment_visit_number(question.id)
    # Only display the first answer
    answer_exist = True if question.answers else False
    answer_text = None
    answer_id = None
    if answer_exist:
        a = question.answers[0]
        answer_text = markdown2.markdown(a.text, extras=["strike"])
        answer_id = a.id
    word = question.text.split(" - ")[-1].strip()
    IPA_transcript = get_IPA(word)
    example_text = (
        markdown2.markdown(question.example, extras=["strike", "tables"])
        if question.example
        else ""
    )
    context = {
        "visit_count": question.visit_count,
        "how_long_ago": how_long_ago,
        "question_text": question.text,
        "question_id": question_id,
        "IPA_transcript": IPA_transcript,
        "word": word,
        "answer_exist": answer_exist,
        "answer_text": answer_text,
        "answer_id": answer_id,
        "example_text": example_text,
    }
    return templates.TemplateResponse(
        request=request, name="question.html.jinja", context=context
    )


@app.get("/delete_question/{question_id}", response_class=HTMLResponse)
async def delete_question(question_id: int):
    db_delete_question(question_id)
    return "200"


@app.get("/delete_audio/{question_id}", response_class=HTMLResponse)
async def delete_audio(question_id: int):
    delete_audio_file(question_id)
    return "200"


@app.get("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer_page(answer_id: int, request: Request):
    answer = db_get_answer_by_id(answer_id)
    if not answer:
        return "404"
    context = {"answer_text": answer.text, "answer_id": answer_id}
    return templates.TemplateResponse(
        request=request, name="edit_answer.html.jinja", context=context
    )


@app.post("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer(
    answer_id: int, form_data: EditAnswerForm = Depends(EditAnswerForm.as_form)
):
    updated_text = form_data.answer_text
    if question_id := db_update_answer_text(answer_id, updated_text):
        return RedirectResponse(url=f"/question/{question_id}", status_code=303)


@app.get("/edit_example/{question_id}", response_class=HTMLResponse)
async def edit_example_page(question_id: int, request: Request):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"

    context = {
        "question_id": question_id,
        "question_example": question.example or "",
    }
    return templates.TemplateResponse(
        request=request, name="edit_example.html.jinja", context=context
    )


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
async def add_question_page(request: Request):

    return templates.TemplateResponse(
        request=request, name="add_question.html.jinja"
    )


@app.post("/add_question", response_class=HTMLResponse)
async def add_question(
    form_data: AddQuestionForm = Depends(AddQuestionForm.as_form),
):
    updated_text = form_data.question_text
    updated_text = updated_text.strip()
    try:
        if q_id := db_add_question(updated_text):
            return RedirectResponse(url=f"/question/{q_id}", status_code=303)
    except IntegrityError:
        return "Question text UNIQUE constraint failed"


@app.get("/add_answer", response_class=HTMLResponse)
async def add_answer_page(qid: int, request: Request):

    context = {"qid": qid}
    return templates.TemplateResponse(
        request=request, name="add_answer.html.jinja", context=context
    )


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
