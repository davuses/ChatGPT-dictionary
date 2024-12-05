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
function deleteQuestionMainPage(button, questionId) {
  var questionText =
    button.parentElement.previousElementSibling.previousElementSibling
      .textContent;
  if (
    confirm("Are you sure you want to delete this question?\n> " + questionText)
  ) {
    fetch("/delete_question/" + questionId).then((Response) => {
      if (Response.ok) {
        var row = button.parentNode.parentNode;
        row.parentNode.removeChild(row);
      }
    });
  }
}
function deleteQuestion(questionId) {
  if (confirm("Are you sure you want to delete this question?")) {
    fetch("/delete_question/" + questionId).then((Response) => {
      if (Response.ok) {
        location.reload();
      }
    });
  }
}
function deleteAudio(questionId) {
  if (confirm("Are you sure you want to delete this audio?")) {
    fetch("/delete_audio/" + questionId).then((Response) => {
      if (Response.ok) {
        location.reload();
      }
    });
  }
}
function playEdgeTTS(button, questionId) {
  fetch("/tts_question/" + questionId).then((Resp) => {
    if (Resp.ok) {
      var audio = document.createElement("audio");
      audio.controls = true;
      audio.className = "svelte-eemfgq";
      audio.style.display = "block";
      audio.src = `/audio/${questionId}-edge.mp3`;
      button.parentNode.insertBefore(audio, button.nextSibling);
      audio.play();
    }
  });
}

function ttsCanPlay() {
  let tts_div = document.getElementById("tts-div");
  if (tts_div) {
    tts_div.style.display = "block";
  }
}

const editPagePattern = /\/edit_.*?(\d+)|add_.*/;

if (editPagePattern.test(window.location.href)) {
  document.addEventListener("DOMContentLoaded", function () {
    var editor = new EasyMDE({
      autofocus: true,
      spellChecker: false,
      nativeSpellcheck: true,
      inputStyle: "contenteditable",
      toolbar: [
        "bold",
        "italic",
        "strikethrough",
        "quote",
        "|",
        "unordered-list",
        "ordered-list",
        "link",
        "table",
        "heading",
        "|",
        "preview",
        "side-by-side",
        "fullscreen",
      ],
    });
    const mdEditors = document.querySelectorAll(".CodeMirror");
    mdEditors.forEach(function (mdEditor) {
      mdEditor.addEventListener("keydown", function (event) {
        if (event.shiftKey && event.key === "Enter") {
          event.preventDefault();
          const form = mdEditor.closest("form");
          if (form) {
            form.submit();
          }
        }
      });
    });
  });
}

const questionUrlPattern = /\/question\/(\d+)/;

// Question page keyboard shortcuts: alt+v, b, e, D, p
if (questionUrlPattern.test(window.location.href)) {
  document.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "v") {
      event.preventDefault();
      const answerDiv = document.getElementById("answer-div");
      if (!answerDiv) {
        navigator.clipboard
          .readText()
          .then((text) => {
            const answerForm = document.createElement("form");
            answerForm.method = "post";
            answerForm.action = "/add_answer";
            let formData = { question_id: questionId, answer_text: text };
            for (const key in formData) {
              const hiddenField = document.createElement("input");
              hiddenField.type = "hidden";
              hiddenField.name = key;
              hiddenField.value = formData[key];
              answerForm.appendChild(hiddenField);
            }
            document.body.appendChild(answerForm);
            answerForm.submit();
          })
          .catch((error) => {
            console.error("Failed to read clipboard: ", error);
          });
      }
    } else if (event.key === "b") {
      let length = history.length;
      for (step = length - 1; step > 0; step--) {
        history.back(step);
      }
    } else if (event.key === "e") {
      document.getElementById("edit-example").click();
    } else if (event.key === "D") {
      document.getElementById("dbt").click();
    }
  });
}

if (
  window.location.pathname === "/" ||
  questionUrlPattern.test(window.location.href)
) {
  document.addEventListener("keydown", (event) => {
    if (event.key === "a") {
      window.location.href = "/add_question";
    } else if (event.key === "A") {
      window.open("/add_question", "_blank").focus();
    }
  });
}

function highlightTableRow(row) {
  const previouslySelectedRow = document.querySelector("tr.selected");
  if (previouslySelectedRow) {
    previouslySelectedRow.classList.remove("selected");
  }
  row.classList.add("selected");
}

if (window.location.pathname === "/") {
  document.addEventListener("DOMContentLoaded", function () {
    const rows = document.querySelectorAll("table tr");
    for (let i = 0; i < rows.length; i++) {
      rows[i].onclick = function () {
        highlightTableRow(this);
      };
    }
  });
}

function load_more() {
  if ((window.location.pathname == "/") & (window.location.search !== "")) {
    return;
  }
  const table = document.querySelector("table");
  const tableBody = document.querySelector("tbody");

  // Get the last <tr> of the table
  const lastRow = table.querySelector("tr:last-child");

  // Get the first <td> of the last <tr>
  const firstCell = lastRow.querySelector("td:first-child");

  // Get the <a> element inside the first <td>
  const linkElement = firstCell.querySelector("a");
  const href = linkElement.href;
  const qid = href.split("/").pop();

  fetch(`/load_more/${qid}`)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      return response.json(); // Assuming the response is JSON
    })
    .then((data) => {
      const q_lists = data["q_lists"];
      q_lists.forEach((q_list) => {
        const row = document.createElement("tr");
        row.innerHTML = `
      <td>
          <label class="unselectable">-<span data-content=" "></span></label>
          <a style="text-decoration: none;"
              href="question/${q_list[0]}">${q_list[1]}</a>
      </td>
      <td>${q_list[2]}</td>
      <td>
          <button onclick="deleteQuestionMainPage(this, ${q_list[0]})"
              >Delete</button>
      </td>
      <td class="visit-${q_list[3]}">${q_list[3]}</td>
  `;
        row.onclick = function () {
          highlightTableRow(this);
        };
        tableBody.appendChild(row);
      });
    })
    .catch((error) => {
      console.error("Error fetching data:", error);
    });
}
