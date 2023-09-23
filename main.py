import markdown2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from database import delete_question, get_all_question, get_question_by_id

app = FastAPI()


def shorten_string(s, max_length=180):
    if len(s) <= max_length:
        return s
    else:
        return s[: max_length - 3] + "..."


@app.get("/", response_class=HTMLResponse)
async def root():
    questions = get_all_question()
    questions = [q for q in questions if not q.is_hidden]
    trs = []
    # questions = sorted(questions, key=lambda q: len(q.text))
    for question in questions:
        tr = (
            '<tr><td><a style="text-decoration: none;"'
            f' href="/question/{question.id}">{shorten_string(question.text)} </a></td><td><button'
            ' onclick="deleteQuestion(this,'
            f' {question.id})">Delete</button></td></tr>'
        )
        trs.append(tr)
    trs_html = "".join(trs)

    script_html = """\

        <script>
        function deleteQuestion(button, questionId) {
            fetch("/delete/" + questionId).then((Response) => {
            if (Response.ok) {
                var row = button.parentNode.parentNode;
                row.parentNode.removeChild(row);
            }
            });
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
        <h1>Questions</h1>
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


@app.get("/question/{question_id}", response_class=HTMLResponse)
async def get_question(question_id: int):
    question = get_question_by_id(question_id)
    if not question:
        return "404"
    answers_li_html = "".join(
        [f"<li>{markdown2.markdown(a.text)}</li>" for a in question.answers]
    )
    html = f"""\
<!DOCTYPE html>
<html>
<head>
    <title>Question Page</title>
</head>
<body>
    <h1>Question and Answers</h1>
    
    <h2>Question:</h2>
    <p id="question">{question.text}</p>
    
    <h2>Answers:</h2>
    <ul>
        {answers_li_html}
    </ul>
</body>
</html>

"""
    return html


@app.get("/delete/{question_id}", response_class=HTMLResponse)
async def delete(question_id: int):
    delete_question(question_id)
    return "200"
