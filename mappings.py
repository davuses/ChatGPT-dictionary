import json


def get_answer(message):
    if message["author"]["role"] == "assistant":
        answer_text = message["content"]["parts"][0]
        return answer_text
    return ""


def get_answer_from_system_node(chat_nodes, node):
    child_id = node["children"][0]
    child_node = chat_nodes[child_id]
    if not child_node["message"]["author"]["role"] == "assistant":
        return ""
    if child_message := child_node["message"]:
        answer = get_answer(child_message)
        return answer
    return ""


def extend_mappings_from_conv(
    conv, meanings_mapping: dict[str, list[str]], skipped_questions: list
):
    question_count = 0
    chat_nodes = conv["mapping"]
    for node in chat_nodes.values():
        if message := node["message"]:
            role = message["author"]["role"]
            if role == "user":
                parts = message["content"]["parts"]
                question: str = parts[0]
                if not question.strip():
                    continue
                if question in skipped_questions:
                    continue
                question_count = question_count + 1
                children_id = node["children"]
                answers = []
                for child_id in children_id:
                    child_node = chat_nodes[child_id]
                    if child_node["message"]["author"]["role"] == "system":
                        answer = get_answer_from_system_node(
                            chat_nodes, child_node
                        )
                        answers.append(answer)
                    elif child_message := child_node["message"]:
                        answer = get_answer(child_message)
                        answers.append(answer)
                if meanings_mapping.get(question) is None:
                    meanings_mapping[question] = answers
    print("questions count in this conv:", question_count)


def get_question_answer_mappings(file="new_conversations.json"):
    conversations_file = file

    conversations = json.load(open(conversations_file, "r", encoding="utf-8"))
    with open("skipped_questions.txt", "r") as f:
        skipped_questions = [l.strip() for l in f.readlines()]
    with open(file, "r") as f, open("prompt.txt", "r") as prompt_f:
        file_content = f.read()
        prompt_text = prompt_f.read()
        assert prompt_text in file_content
    question_answer_mappings: dict[str, list[str]] = {}
    for i, conv in enumerate(conversations):
        print("conversation", i)
        extend_mappings_from_conv(
            conv, question_answer_mappings, skipped_questions
        )

    return question_answer_mappings
