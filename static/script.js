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
// document.addEventListener("click", function (event) {
//   if (!event.target.matches(".playButton")) return;
//   var button = event.target;
//   var playId = button.getAttribute("play-id");
//   var audioSrc = `/audio/${playId}.mp3`;
//   var audio = document.createElement("audio");
//   audio.controls = true;
//   audio.style.display = "block";
//   audio.src = audioSrc;
//   button.parentNode.insertBefore(audio, event.target.nextSibling);
//   // var audio = new Audio(audioSrc);
//   audio.play();
// });
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
// Function to handle form submission when Alt+V is pressed
function handleAltV(event) {
  if (event.altKey && event.key === "v") {
    event.preventDefault(); // Prevent default behavior of pasting text
    const answerForm = document.getElementById("hidden-a-form");
    const answerTextArea = answerForm.querySelector(
      'textarea[name="answer_text"]'
    );
    const answerUl = document.getElementById("answer-ul");

    // Check if the answer-ul has no child elements
    if (answerUl.children.length === 0) {
      // Access clipboard data
      navigator.clipboard
        .readText()
        .then((text) => {
          // Set clipboard text to textarea value
          answerTextArea.value = text;
          // Submit the form
          answerForm.submit();
        })
        .catch((error) => {
          console.error("Failed to read clipboard: ", error);
        });
    }
  }
}

// Add event listener to listen for key presses
const urlPattern = /\/question\/(\d+)/;
if (urlPattern.test(window.location.href)) {
  document.addEventListener("keydown", handleAltV);
}
