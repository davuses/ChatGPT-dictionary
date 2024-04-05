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
  var questionText = button.parentElement.previousElementSibling.previousElementSibling.textContent;
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
document.addEventListener("click", function (event) {
  if (!event.target.matches(".playButton")) return;
  var button = event.target;
  var playId = button.getAttribute("play-id");
  var audioSrc = `/audio/${playId}.wav`;
  var audio = document.createElement("audio");
  audio.controls = true;
  audio.style.display = "block";
  audio.src = audioSrc;
  button.parentNode.insertBefore(audio, event.target.nextSibling);
  // var audio = new Audio(audioSrc);
  audio.play();
});
