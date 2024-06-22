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
      audio.style.display = "block";
      audio.src = `/audio/${questionId}-edge.mp3`;
      button.parentNode.insertBefore(audio, button.nextSibling);
      audio.play();
    }
  });
}
document.addEventListener("DOMContentLoaded", function () {
  const textareas = document.querySelectorAll(".submit-on-shift-enter");
  textareas.forEach(function (textarea) {
    textarea.addEventListener("keydown", function (event) {
      if (event.shiftKey && event.key === "Enter") {
        event.preventDefault(); // Prevents the default behavior of adding a new line
        const form = textarea.closest("form");
        if (form) {
          form.submit(); // Submit the form
        }
      }
    });
  });
});

function myOnCanPlayFunction() {
  let second_ipa_audio = document.getElementById("2nd-ipa-audio");
  if (second_ipa_audio) {
    if (second_ipa_audio.readyState) {
      second_ipa_audio.style.display = "inline";
    }
  }
  let first_ipa_audio = document.getElementById("1st-ipa-audio");
  if (first_ipa_audio) {
    if (first_ipa_audio.readyState) {
      first_ipa_audio.style.display = "inline";
    }
  }
}

function ttsCanPlay() {
  let tts_div = document.getElementById("tts-div");
  if (tts_div) {
    tts_div.style.display = "block";
  }
}

const questionUrlPattern = /\/question\/(\d+)/;

if (questionUrlPattern.test(window.location.href)) {
  document.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "v") {
      event.preventDefault();
      const answerForm = document.getElementById("hidden-a-form");
      const answerTextArea = answerForm.querySelector(
        'textarea[name="answer_text"]'
      );
      const answerUl = document.getElementById("answer-ul");

      if (answerUl.children.length === 0) {
        navigator.clipboard
          .readText()
          .then((text) => {
            answerTextArea.value = text;

            answerForm.submit();
          })
          .catch((error) => {
            console.error("Failed to read clipboard: ", error);
          });
      }
    } else if (event.key === "b") {
      let url = new URL(document.referrer);
      if (/\/edit_example\/(\d+)/.test(url.pathname)) {
        history.go(-3);
      } else if (url.pathname === "/") {
        history.go(-1);
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
