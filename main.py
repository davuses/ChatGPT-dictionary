import markdown2
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from database import (
    db_delete_answer,
    db_delete_question,
    db_get_all_question,
    db_get_answer_by_id,
    db_get_question_by_id,
    db_update_answer_text,
    db_update_question_text,
)

app = FastAPI()


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


def shorten_string(s, max_length=180):
    if len(s) <= max_length:
        return s
    else:
        return s[: max_length - 3] + "..."


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    questions = db_get_all_question()
    questions = [q for q in questions if not q.is_hidden]
    questions_count = len(questions)
    trs = []
    if request.query_params.get("sort") == "length":
        questions = sorted(questions, key=lambda q: len(q.text))
    for question in questions:
        tr = (
            '<tr><td><a style="text-decoration: none;"'
            f' href="/question/{question.id}">{shorten_string(question.text)} </a></td><td><button'
            ' onclick="deleteQuestion(this,'
            f' {question.id})">Delete</button></td></tr>'
        )
        trs.append(tr)
    trs_html = "".join(trs)
    sort_link_url = "/?sort=length"
    sort_link = (
        '<a href="/" style="text-decoration: none";>Sort by Date</a>'
        f' &nbsp&nbsp&nbsp&nbsp&nbsp<a href="{sort_link_url}"'
        ' style="text-decoration: none;">Sort by Length</a>'
    )
    script_html = """\
        <script>
            function deleteQuestion(button, questionId) {
            if (confirm("Are you sure you want to delete this question?")) {
                fetch("/delete_question/" + questionId).then((Response) => {
                if (Response.ok) {
                    var row = button.parentNode.parentNode;
                    row.parentNode.removeChild(row);
                }
                });
            }
            }
        </script>
        """

    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>Questions Table</title>
        </head>
        <body>
            <h1>{questions_count} Questions</h1>
            <p>{sort_link}</p>
            <table border="1">
            <tr>
                <th>Question</th>
                <th>Action</th>
            </tr>
                {trs_html}
            <!-- Add more questions as needed -->
            </table>
            {script_html}
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
        <textarea name="question_text" rows="4" cols="50">{question.text}</textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Question</title>
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
async def get_question(question_id: int):
    question = db_get_question_by_id(question_id)
    if not question:
        return "404"
    answers_li_html = "".join(
        [
            f"<li>{markdown2.markdown(a.text)}"
            f"""<button onclick="location.href='/edit_answer/{a.id}'" type="button">Edit</button>"""
            "&nbsp&nbsp&nbsp"
            '<button onclick="deleteAnswer(this,'
            f' {a.id})">Delete</button></li>'
            # '<a href="javascript:void(0);"'
            # f' onclick="confirmDeletion({a.id})">Delete</a>'
            for a in question.answers
        ]
    )
    script_html = """
        <script>
            function deleteAnswer(button, answerId) {
                if (confirm("Are you sure you want to delete this answer?")) {
                    fetch("/delete_answer/" + answerId).then((Response) => {
                    if (Response.ok) {
                        var a_li = button.parentNode;
                        var a_ul = a_li.parentNode;
                        a_ul.removeChild(a_li);
                    }
                    });
                }
            }
        </script>
        """
    html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>Question Page</title>
            {script_html}
        </head>
        <body>
            <a href="/">Back to Questions</a>
            <h1>Question and Answers</h1>
            
            <h2>Question:</h2>
            <p id="question">{question.text}</p>
            <button onclick="location.href='/edit_question/{question_id}'" type="button">Edit</button>
            <h2>Answers:</h2>
            <ul>
                {answers_li_html}
            </ul>
        </body>
        </html>
        """
    return html


@app.get("/delete_question/{question_id}", response_class=HTMLResponse)
async def delete_question(question_id: int):
    db_delete_question(question_id)
    return "200"


@app.get("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer_page(answer_id: int):
    # Replace this with your actual function to fetch answer by ID
    answer = db_get_answer_by_id(answer_id)
    if not answer:
        return "404"
    form_html = f"""\
    <form method="post" action="/edit_answer/{answer_id}">
        <textarea name="answer_text" rows="4" cols="50">{answer.text}</textarea><br>
        <input type="submit" value="Submit">
    </form>
    """

    html = f"""\
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Answer</title>
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


@app.get("/delete_answer/{answer_id}", response_class=HTMLResponse)
async def delete_answer(answer_id: int):
    if question_id := db_delete_answer(answer_id):
        return RedirectResponse(url=f"/question/{question_id}", status_code=303)
